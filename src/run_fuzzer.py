#!/usr/bin/env python3
"""
Python wrapper for secure monitor fuzzing.

Consider the following environment variables.

SMFUZZ_TRACE=[0,1] (default: 0)
- disables/enables qemu tracing (generates *a lot* of output)

SMFUZZ_AFL_PATH (default: system-wide `afl-fuzz` from `$PATH`)
- the afl++ binary used for fuzzing

SMFUZZ_QEMU_SYSTEM_PATH (default: system-wide `qemu-system-aarch64` from `$PATH`)
- the full-system qemu emulator binary to be used

SMFUZZ_HARNESS_PATH (default: `/out/generic_harness.so`)
- the fuzzing harness to be used
"""
import sys
import os
import argparse
import subprocess
import socket
import logging

################################################################################
# CONFIGURE LOGGING
################################################################################

FORMAT = (
            "%(asctime)s,%(msecs)d %(levelname)-8s "
                "[%(filename)s:%(lineno)d] %(message)s"
                )
logging.basicConfig(
            format=FORMAT, datefmt="%Y-%m-%d:%H:%M:%S", level=logging.DEBUG
            )

log = logging.getLogger(__name__)


################################################################################
# RUN FUZZER
################################################################################

class FuzzProfile:
    def __init__(self, entry_addr, hook_addr, code_start_addr, code_end_addr, fuzz_binary_path, fuzz_hook_path, qemu_profile, afl_out_dir, afl_in_dir):
        self.entry_addr = entry_addr
        self.hook_addr = hook_addr
        self.code_start_addr = code_start_addr
        self.code_end_addr = code_end_addr
        self.fuzz_binary_path = fuzz_binary_path
        self.fuzz_hook_path = fuzz_hook_path
        self.qemu_profile = qemu_profile
        self.afl_out_dir = afl_out_dir
        self.afl_in_dir = afl_in_dir
        

class QemuProfile:
    def __init__(self, qemu_binary_path, qemu_config_path, qemu_logging_path, qemu_snapshot_path):
        self.qemu_binary_path = qemu_binary_path
        self.qemu_config_path = qemu_config_path
        self.qemu_logging_path = qemu_logging_path
        self.qemu_snapshot_path = qemu_snapshot_path


def build_qemu_cmd_line(qemu_profile):
    # TODO better check if attributes are really set and only add then
    # add -d exec,cpu,int,in_asm if you want more logging
    snap = qemu_profile.qemu_snapshot_path
    cmd_line = [qemu_profile.qemu_binary_path, 
                "-machine configurable",
                "-kernel",
                qemu_profile.qemu_config_path,
                f"-D {qemu_profile.qemu_logging_path}",
                "-serial tcp:localhost:2000",
                "-serial tcp:localhost:2002",
                "-semihosting-config enable,target=native",
                "--accel tcg,thread=single",
                "-nographic",
                "-monitor tcp:127.0.0.1:3334,server,nowait",
                "-S",
                f"-blockdev node-name=node-A,driver=qcow2,file.driver=file,file.node-name=file,file.filename={snap}"] 

    is_trace = os.getenv("SMFUZZ_TRACE", 0)
    if is_trace:
        cmd_line.append("-d exec,in_asm,cpu")

    return " ".join(cmd_line)


def build_fuzz_cmd_line(fuzz_profile):
    target_cmd = build_qemu_cmd_line(fuzz_profile.qemu_profile)
    cmd_line = [fuzz_profile.fuzz_binary_path]
    if "afl-fuzz" in fuzz_profile.fuzz_binary_path:
        cmd_line.append("-V 86400")

    cmd_line.extend(["-t 100",
                     "-i " + fuzz_profile.afl_in_dir,
                     "-o " + fuzz_profile.afl_out_dir,
                     "-QQ",
                     "--",
                     target_cmd])

    return " ".join(cmd_line)


def get_fuzzer_env(fuzz_profile):
    fuzz_env = os.environ.copy()
    fuzz_env["AFL_ENTRY"] = fuzz_profile.entry_addr
    fuzz_env["AFL_CODE_START"] = fuzz_profile.code_start_addr
    fuzz_env["AFL_CODE_END"] = fuzz_profile.code_end_addr
    fuzz_env["AFL_QEMU_PERSISTENT_ADDR"] = fuzz_profile.hook_addr
    fuzz_env["AFL_QEMU_PERSISTENT_HOOK"] = fuzz_profile.fuzz_hook_path
    
    fuzz_env["AFL_SKIP_BIN_CHECK"] = "1"
    fuzz_env["AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES"] = "1"
    fuzz_env["AFL_SKIP_CPUFREQ"] = "1"
    fuzz_env["AFL_NO_AFFINITY"] = "1"
    if os.getenv("SMFUZZ_AFL_DEBUG") == "1":
        fuzz_env["AFL_DEBUG"] = "1"
    if os.getenv("SMFUZZ_AFL_NO_UI") == "1":
        fuzz_env["AFL_NO_UI"] = "1"
    return fuzz_env


def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Define target to be fuzzed.")
    return parser


def main():
    arg_parser = setup_args()
    args = arg_parser.parse_args()
    
    # Take `afl-fuzz` from `$SMFUZZ_AFL_PATH`, default to `$PATH`
    fuzz_binary_path = os.getenv("SMFUZZ_AFL_PATH", "afl-fuzz")

    # Take `qemu-system-aarch64` from `$SMFUZZ_QEMU_SYSTEM_PATH`, default to `$PATH`
    qemu_binary_path = os.getenv("SMFUZZ_QEMU_SYSTEM_PATH", "qemu-system-aarch64")

    fuzz_hook_path = os.getenv("SMFUZZ_HARNESS_PATH", "/src/manual-harness/generic_harness.so")
    print(fuzz_hook_path)

    afl_out_dir = os.getenv("SMFUZZ_AFL_OUT_DIR", f"/out/afl-out")

    afl_in_dir = os.getenv("SMFUZZ_AFL_IN_DIR", f"/in/afl-in")

    if not os.path.isfile(fuzz_hook_path):
        log.error(f"{fuzz_hook_path} does not exist.")
        sys.exit()

    qemu_config_path = "/out/qemu_conf.json"
    qemu_logging_path = "/out/qemu-fuzzing-logging.log"
    qemu_snapshot_path = "/out/snapshot.qcow2"
    
    qemu_snapshot_tag = "booted"
    
    qemu_profile = QemuProfile(qemu_binary_path, qemu_config_path, qemu_logging_path, qemu_snapshot_path)
    
    # TODO a better approach would be to define the profiles from outside
    # for now those targets are supported -> can be done better later
    if args.target == "samsung-s6":
        fuzz_profile = FuzzProfile("0x02134000", "0x0210f400", "0x0", "0xffffffff", fuzz_binary_path, fuzz_hook_path, qemu_profile, afl_out_dir, afl_in_dir)
    elif args.target == "huawei-p20lite":
        fuzz_profile = FuzzProfile("0x00480000", "0x35e1ac04", "0x0", "0xffffffff", fuzz_binary_path, fuzz_hook_path, qemu_profile, afl_out_dir, afl_in_dir)
    elif args.target == "intel-n5x":
        fuzz_profile = FuzzProfile("0x00480000", "0x0000bc00", "0x0", "0xffffffff", fuzz_binary_path, fuzz_hook_path, qemu_profile, afl_out_dir, afl_in_dir)
    elif args.target == "nxp-imx8mq":
        fuzz_profile = FuzzProfile("0x40200000", "0x00918c04", "0x0", "0xffffffff", fuzz_binary_path, fuzz_hook_path, qemu_profile, afl_out_dir, afl_in_dir)
    elif args.target == "samsung-s7":
        fuzz_profile = FuzzProfile("0x02048000", "0x02031c00", "0x0", "0xffffffff", fuzz_binary_path, fuzz_hook_path, qemu_profile, afl_out_dir, afl_in_dir)
    elif args.target == "xilinx-zynqmp":
        fuzz_profile = FuzzProfile("0x08000000", "0xffff1c00", "0x0", "0xffffffff", fuzz_binary_path, fuzz_hook_path, qemu_profile, afl_out_dir, afl_in_dir)
    elif args.target == "nvidia-t186":
        fuzz_profile = FuzzProfile("0x80000000", "0x3000dc00", "0x0", "0xffffffff", fuzz_binary_path, fuzz_hook_path, qemu_profile, afl_out_dir, afl_in_dir)
    else:
        print("Unknown target selected...")
        exit(-1)
    
    #print(build_fuzz_cmd_line(fuzz_profile).split(" "))
    # run fuzzer with env
    p = subprocess.Popen(build_fuzz_cmd_line(fuzz_profile).split(" "), env=get_fuzzer_env(fuzz_profile))
    
    # connect to qemu monitor and load snapshot
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    # try to connect until qemu machine is up
    while s.connect_ex(("127.0.0.1", 3334)) != 0:
        pass
    # load snapshot with defined tag
    s.send(str.encode("loadvm " + qemu_snapshot_tag + "\n"))
    # start qemu machine
    s.send(str.encode("c\n"))

    try:
        p.wait()
    except KeyboardInterrupt:
        p.terminate()

if __name__ == '__main__':
    main()
