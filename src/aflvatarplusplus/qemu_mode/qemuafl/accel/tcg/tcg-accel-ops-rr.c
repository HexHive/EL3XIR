/*
 * QEMU TCG Single Threaded vCPUs implementation
 *
 * Copyright (c) 2003-2008 Fabrice Bellard
 * Copyright (c) 2014 Red Hat Inc.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"
#include "qemu-common.h"
#include "sysemu/tcg.h"
#include "sysemu/replay.h"
#include "qemu/main-loop.h"
#include "qemu/guest-random.h"
#include "exec/exec-all.h"
#include "hw/boards.h"

#include "tcg-accel-ops.h"
#include "tcg-accel-ops-rr.h"
#include "tcg-accel-ops-icount.h"

#include "qemuafl/common.h"

/* Kick all RR vCPUs */
void rr_kick_vcpu_thread(CPUState *unused)
{
    CPUState *cpu;

    CPU_FOREACH(cpu) {
        cpu_exit(cpu);
    };
}

/*
 * TCG vCPU kick timer
 *
 * The kick timer is responsible for moving single threaded vCPU
 * emulation on to the next vCPU. If more than one vCPU is running a
 * timer event with force a cpu->exit so the next vCPU can get
 * scheduled.
 *
 * The timer is removed if all vCPUs are idle and restarted again once
 * idleness is complete.
 */

static QEMUTimer *rr_kick_vcpu_timer;
static CPUState *rr_current_cpu;

#define TCG_KICK_PERIOD (NANOSECONDS_PER_SECOND / 10)

static inline int64_t rr_next_kick_time(void)
{
    return qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + TCG_KICK_PERIOD;
}

/* Kick the currently round-robin scheduled vCPU to next */
static void rr_kick_next_cpu(void)
{
    CPUState *cpu;
    do {
        cpu = qatomic_mb_read(&rr_current_cpu);
        if (cpu) {
            cpu_exit(cpu);
        }
    } while (cpu != qatomic_mb_read(&rr_current_cpu));
}

static void rr_kick_thread(void *opaque)
{
    timer_mod(rr_kick_vcpu_timer, rr_next_kick_time());
    rr_kick_next_cpu();
}

static void rr_start_kick_timer(void)
{
    if (!rr_kick_vcpu_timer && CPU_NEXT(first_cpu)) {
        rr_kick_vcpu_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                           rr_kick_thread, NULL);
    }
    if (rr_kick_vcpu_timer && !timer_pending(rr_kick_vcpu_timer)) {
        timer_mod(rr_kick_vcpu_timer, rr_next_kick_time());
    }
}

static void rr_stop_kick_timer(void)
{
    if (rr_kick_vcpu_timer && timer_pending(rr_kick_vcpu_timer)) {
        timer_del(rr_kick_vcpu_timer);
    }
}

static void rr_wait_io_event(void)
{
    CPUState *cpu;

    while (all_cpu_threads_idle()) {
        rr_stop_kick_timer();
        qemu_cond_wait_iothread(first_cpu->halt_cond);
    }

    rr_start_kick_timer();

    CPU_FOREACH(cpu) {
        qemu_wait_io_event_common(cpu);
    }
}

/*
 * Destroy any remaining vCPUs which have been unplugged and have
 * finished running
 */
static void rr_deal_with_unplugged_cpus(void)
{
    CPUState *cpu;

    CPU_FOREACH(cpu) {
        if (cpu->unplug && !cpu_can_run(cpu)) {
            tcg_cpus_destroy(cpu);
            break;
        }
    }
}

static QemuThread *single_tcg_cpu_thread;

void gotPipeNotification(void *ctx)
{
    //qemu_mutex_lock_iothread();
    qemu_log("PIPE Notification here!!!\n");
    CPUArchState *env;
    char buf[4];

    /* cpu thread asked us to run AFL forkserver */
    if(read(afl_qemuloop_pipe[0], buf, 4) != 4) {
        qemu_log("error reading afl/qemu pipe!\n");
        exit(1);
    }

    qemu_log("PIPE Notification start up afl forkserver! pid %d\n", getpid());
    afl_setup();
    env = NULL; //XXX for now.. if we want to share JIT to the parent we will need to pass in a real env here
    //env = restart_cpu->env_ptr;
    afl_forkserver(restart_cpu);

    /* we're now in the child! */
    //tcg_cpu_thread = NULL;
    //(CPUState *)(first_cpu) = restart_cpu;

    //qemu_log("PIPE Notification after afl fork being CHILD %d \n", getpid());
    //restart_cpu->as = NULL;

    single_tcg_cpu_thread = NULL;
    
    (&cpus)->tqh_first = restart_cpu;


    qemu_init_vcpu(restart_cpu);

    //qemu_clock_warp(QEMU_CLOCK_VIRTUAL);
    /* continue running iothread in child process... */
}

/*
 * In the single-threaded case each vCPU is simulated in turn. If
 * there is more than a single vCPU we create a simple timer to kick
 * the vCPU and ensure we don't get stuck in a tight loop in one vCPU.
 * This is done explicitly rather than relying on side-effects
 * elsewhere.
 */

// to notify mainloop to become forkserver
int afl_qemuloop_pipe[2];
// cpu to restart child with
CPUState *restart_cpu = NULL;

static void *rr_cpu_thread_fn(void *arg)
{
    //qemu_log("rr_cpu_thread_fn start... \n");

    CPUState *cpu = arg;

    assert(tcg_enabled());
    rcu_register_thread();
    tcg_register_thread();

    qemu_mutex_lock_iothread();
    qemu_thread_get_self(cpu->thread);

    cpu->thread_id = qemu_get_thread_id();
    cpu->can_do_io = 1;
    cpu_thread_signal_created(cpu);
    qemu_guest_random_seed_thread_part2(cpu->random_seed);

    //current_cpu = cpu;
    //qemu_log("rr_cpu_thread_fn waiting for initial kick-off... \n");

    /* wait for initial kick-off after machine start */
    // dont wait for init if we are an afl child
    if(!afl_fork_child)  {
        while (first_cpu->stopped) {
            qemu_cond_wait_iothread(first_cpu->halt_cond);

            /* process any pending work */
            CPU_FOREACH(cpu) {
                current_cpu = cpu;
                qemu_wait_io_event_common(cpu);
            }
        }
    }

    rr_start_kick_timer();

    cpu = first_cpu;

    /* process any pending work */
    cpu->exit_request = 1;

    //qemu_log("rr_cpu_thread_fn... before loop \n");
    while (1) {
        // as afl child we assume iothread to be unlocked
        if(!afl_fork_child)  {
            qemu_mutex_unlock_iothread();
            replay_mutex_lock();

            qemu_mutex_lock_iothread();
        }

        //if (icount_enabled()) {
            /* Account partial waits to QEMU_CLOCK_VIRTUAL.  */
        //    icount_account_warp_timer();
            /*
             * Run the timers here.  This is much more efficient than
             * waking up the I/O thread and waiting for completion.
             */
        //    icount_handle_deadline();
        //}

        if(!afl_fork_child)  {
            replay_mutex_unlock();
        }

        if(afl_fork_child) {
            cpu->exit_request = 0;
            cpu->stop = false;
            cpu->stopped = false;
        }

        if (!cpu) {
            cpu = first_cpu;
        }

        //qemu_log("rr_cpu_thread_fn... in loop before cpu loop work list empty %d, !exit_request %d\n", cpu_work_list_empty(cpu), !cpu->exit_request);
        while (cpu && cpu_work_list_empty(cpu) && !cpu->exit_request) {
            //qemu_log("rr_cpu_thread_fn begin of cpu loop");
            qatomic_mb_set(&rr_current_cpu, cpu);
            current_cpu = cpu;

            qemu_clock_enable(QEMU_CLOCK_VIRTUAL,
                              (cpu->singlestep_enabled & SSTEP_NOTIMER) == 0);
            //qemu_log("rr_cpu_thread_fn... inside cpu loop %d \n", cpu_can_run(cpu));
            if (cpu_can_run(cpu)) {
                int r;

                qemu_mutex_unlock_iothread();
                //if (icount_enabled()) {
                //    icount_prepare_for_run(cpu);
                //}
                //qemu_log("rr_thread executing tcg cpus exec \n");
                r = tcg_cpus_exec(cpu);
                //qemu_log("rr_thread executing cpu exec return 0x%lx \n", r);
                //if (icount_enabled()) {
                //    icount_process_data(cpu);
                //}
                qemu_mutex_lock_iothread();

                if (r == EXCP_DEBUG) {
                    cpu_handle_guest_debug(cpu);
                    break;
                } else if (r == EXCP_ATOMIC) {
                    qemu_mutex_unlock_iothread();
                    cpu_exec_step_atomic(cpu);
                    qemu_mutex_lock_iothread();
                    break;
                } else if (r == AFL_ENTRY_HIT) {
                    qemu_log("Hit afl cpu loop\n");
                    // ask to run forkserver
                    
                    // save context of cpu
                    restart_cpu = (&cpus)->tqh_first;

                    (&cpus)->tqh_first = NULL;

                    // notify iothread
                    if(write(afl_qemuloop_pipe[1], "FORK", 4) != 4) {
                        qemu_log("write afl_qemuloop_pipe failed\n");
                    }
                    afl_qemuloop_pipe[1] = -1;


                    //qatomic_set(&rr_current_cpu, NULL);

                    //restart_cpu->thread = NULL;
                    //cpu->thread = NULL;

                    //qatomic_mb_set(&cpu->exit_request, 0);

                    qemu_log("Waiting cpu thread for io event then exit...\n");

                    //qemu_notify_event();

                    qemu_wait_io_event(cpu);

                    //tcg_cpus_destroy(cpu);
                    //rr_deal_with_unplugged_cpus();

                    //rcu_unregister_thread();

                    qemu_mutex_unlock_iothread();
                    rcu_unregister_thread();
                    sleep(1);
                    return NULL;
                }
                //qemu_log("rr_thread executing cpu exec after if\n");
            } else if (cpu->stop) {
                if (cpu->unplug) {
                    cpu = CPU_NEXT(cpu);
                }
                break;
            }

            //cpu = CPU_NEXT(cpu);
        } /* while (cpu && !cpu->exit_request).. */

        /* Does not need qatomic_mb_set because a spurious wakeup is okay.  */
        qatomic_set(&rr_current_cpu, NULL);

        if (cpu && cpu->exit_request) {
            qatomic_mb_set(&cpu->exit_request, 0);
        }

        if (icount_enabled() && all_cpu_threads_idle()) {
            /*
             * When all cpus are sleeping (e.g in WFI), to avoid a deadlock
             * in the main_loop, wake it up in order to start the warp timer.
             */
            qemu_notify_event();
        }

        rr_wait_io_event();
        rr_deal_with_unplugged_cpus();
    }

    rcu_unregister_thread();
    return NULL;
}

void rr_start_vcpu_thread(CPUState *cpu)
{
    //qemu_log("rr_start_vcpu_thread... \n");
    char thread_name[VCPU_THREAD_NAME_SIZE];
    static QemuCond *single_tcg_halt_cond;

    g_assert(tcg_enabled());
    parallel_cpus = false;

    if (!single_tcg_cpu_thread) {
        //qemu_log("rr_start_vcpu_thread creating single cpu thread\n");
        cpu->thread = g_malloc0(sizeof(QemuThread));
        cpu->halt_cond = g_malloc0(sizeof(QemuCond));
        qemu_cond_init(cpu->halt_cond);

        /* share a single thread for all cpus with TCG */
        snprintf(thread_name, VCPU_THREAD_NAME_SIZE, "ALL CPUs/TCG");
        qemu_thread_create(cpu->thread, thread_name,
                           rr_cpu_thread_fn,
                           cpu, QEMU_THREAD_JOINABLE);

        single_tcg_halt_cond = cpu->halt_cond;
        single_tcg_cpu_thread = cpu->thread;
#ifdef _WIN32
        cpu->hThread = qemu_thread_get_handle(cpu->thread);
#endif
    } else {
        qemu_log("single_tcg_cpu_thread already exists...\n");
        /* we share the thread */
        cpu->thread = single_tcg_cpu_thread;
        cpu->halt_cond = single_tcg_halt_cond;
        cpu->thread_id = first_cpu->thread_id;
        cpu->can_do_io = 1;
        cpu->created = true;
    }
}
