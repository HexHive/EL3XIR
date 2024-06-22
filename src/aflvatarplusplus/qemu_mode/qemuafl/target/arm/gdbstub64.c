/*
 * ARM gdb server stub: AArch64 specific functions.
 *
 * Copyright (c) 2013 SUSE LINUX Products GmbH
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library; if not, see <http://www.gnu.org/licenses/>.
 */
#include "qemu/osdep.h"
#include "cpu.h"
#include "exec/gdbstub.h"
//very hacky way to get also regs in arm32!
int aarch64_cpu_gdb_read_register(CPUState *cs, GByteArray *mem_buf, int n)
{
    ARMCPU *cpu = ARM_CPU(cs);
    CPUARMState *env = &cpu->env;
    if (env->aarch64)
    {
        if (n < 31)
        {
            /* Core integer register.  */
            return gdb_get_reg64(mem_buf, env->xregs[n]);
        }
        switch (n)
        {
        case 31:
            return gdb_get_reg64(mem_buf, env->xregs[31]);
        case 32:
            return gdb_get_reg64(mem_buf, env->pc);
        case 33:
            return gdb_get_reg32(mem_buf, pstate_read(env));
        }
    }
    else
    {
        //printf("hello arm32\n");
        if (n < 15)
        {
            /* Core integer register.  */
            return gdb_get_reg64(mem_buf, env->regs[n]);
        }
        else if (n < 31)
        {
            return gdb_get_reg64(mem_buf, env->xregs[n]);
        }
        switch (n)
        {
        case 31:
            return gdb_get_reg64(mem_buf, env->xregs[31]);
        case 32:
            return gdb_get_reg64(mem_buf, env->regs[15]);
        case 33:
            return gdb_get_reg32(mem_buf, pstate_read(env));
        }
    }

    /* Unknown register.  */
    return 0;
}

int aarch64_cpu_gdb_write_register(CPUState *cs, uint8_t *mem_buf, int n)
{
    ARMCPU *cpu = ARM_CPU(cs);
    CPUARMState *env = &cpu->env;
    uint64_t tmp;

    tmp = ldq_p(mem_buf);
    if (env->aarch64)
    {
        if (n < 31)
        {
            /* Core integer register.  */
            env->xregs[n] = tmp;
            return 8;
        }
        switch (n)
        {
        case 31:
            env->xregs[31] = tmp;
            return 8;
        case 32:
            env->pc = tmp;
            return 8;
        case 33:
            /* CPSR */
            pstate_write(env, tmp);
            return 4;
        }
    }
    else
    {
      if (n < 15)
        {
            /* Core integer register.  */
            env->regs[n] = (uint32_t) tmp;
            return 8;
        }
        else if(n==15){
            tmp &= ~1;
            env->regs[n] = (uint32_t) tmp;
            return 8;
        }
        else if(n < 31){
            env->xregs[n] = tmp;
            return 8;
        }
        switch (n)
        {
        case 31:
            env->xregs[31] = tmp;
            return 8;
        case 32:
            tmp &= ~1;
            env->regs[15] = (uint32_t) tmp;
            return 8;
        case 33:
            /* CPSR */
            pstate_write(env, tmp);
            return 4;
        }   

    }
    /* Unknown register.  */
    return 0;
}
