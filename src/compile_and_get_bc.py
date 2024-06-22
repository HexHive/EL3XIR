#!/usr/bin/env python3
import argparse
import os
import subprocess


"""
	dependencies
	make sure this is installed
	
	WLLVM:
	git clone https://github.com/travitch/whole-program-llvm.git
	cd whole-program-llvm
	sudo pip install -e .
	
	GCC Toolchain for ARM
	wget https://developer.arm.com/-/media/Files/downloads/gnu-a/10.3-2021.07/binrel/gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf.tar.xz
	tar -xvf gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf.tar.xz
	
	GCC Toolchain for AARCH64
	wget https://developer.arm.com/-/media/Files/downloads/gnu-a/10.3-2021.07/binrel/gcc-arm-10.3-2021.07-x86_64-aarch64-none-linux-gnu.tar.xz
	tar -xvf gcc-arm-10.3-2021.07-x86_64-aarch64-none-linux-gnu.tar.xz
	
	Clang / LLVM for wllvm
	use the one which comes with SVF (or install your own but include in PATH)
	
"""

def compile_kernel(kernel_path, kernel_conf, compile_env):
    cmd_line = "make HOSTCC=clang CC=wllvm " + kernel_conf + "; make -j$(nproc) HOSTCC=clang CC=wllvm all"   
    # currently the kernel configs are:
    #   intelsocfpga: defconfig
    #   imx:          defconfig
    #   zynqmp:       xilinx_zynqmp_defconfig
    #   nvidia:       tegra_defconfig
    
    p = subprocess.Popen(cmd_line, cwd=kernel_path, env=compile_env, shell=True)
    
    try:
        p.wait()
    except KeyboardInterrupt:
        p.terminate()

def get_env_kernel_wllvm():
    # set clang environment
    wllvm_env = os.environ.copy()
    wllvm_env["ARCH"] = "arm64"
    # this is wllvm specific
    wllvm_env["LLVM_COMPILER"] = "clang"
    # just use the clang binary which comes with svf - need to put this in path
    #wllvm_env["PATH"] = os.getcwd() + "/svf/llvm-14.0.0.obj/bin:$" + wllvm_env["PATH"]
    
    wllvm_env["CROSS_COMPILE"] = "aarch64-none-linux-gnu-"
    
    # BINUTILS_TARGET_PREFIX=aarch64-none-linux-gnu
    wllvm_env["BINUTILS_TARGET_PREFIX"] = "aarch64-none-linux-gnu"
     
    return wllvm_env

def recompile_without_opt(compile_cmd, compile_env, kernel_path):

    # include flags to emit llvm and disable optimizations
    compile_cmd = compile_cmd.replace("-O2", "-emit-llvm -mllvm -disable-llvm-optzns -O0 -g")
    compile_cmd = compile_cmd.replace(".o ", ".noopt.bc ")
    # this is necessary for kernels compiled with layout as .tmp_ is added
    compile_cmd = compile_cmd.replace("/.tmp_", "/")

    print(compile_cmd)
    subprocess.run(compile_cmd, cwd=kernel_path, env=compile_env, shell=True)
    return
   
def search_old_commands_and_run_without_opt(kernel_path, kernel_recomp, compile_env):

    # we do not want to recompile the complete kernel - only the ones specified in
    # the subdirectoy
    #sub_path = kernel_path + "/" + kernel_recomp
    
    print("Done compiling, now recompile the specified files without optimization!")

    recomp_files = []
    with open(kernel_recomp) as f:
        for l in f.readlines():
            recomp_files.append(kernel_path + l.split(".noopt.bc")[0])
    print(recomp_files)
    # we go through all files in kernel_path and search for ".filename.o.cmd"
    # if they are part of the recomp file we need to recompile these without optimization
    for subdir, dirs, files in os.walk(kernel_path):
        for file in files:
            filepath = subdir + os.sep + file
            if filepath.endswith(".o.cmd"):
                #print(filepath)
                if filepath.split(".o.cmd")[0].replace("/.", "/") in recomp_files:
                    print(filepath)
                    with open(filepath) as f:
                        compile_cmd = f.readline().split(" := ")[-1]
                        #print(compile_cmd)
                        recompile_without_opt(compile_cmd, compile_env, kernel_path)
            
    # if all object files are recompiled we can recompile modules ".filename.ko.cmd"
    # Do we need to recompile the modules?
    # Problem: If we have multiple modules, linking will fail later on
    # TODO maybe check if all defined files have been recompiled successfully?
    # else linking will fail with "no such file or directory"

    return
   
def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel_dir", help="absolut path to root directory for linux source code")
    parser.add_argument("kernel_conf", help="name for config to compile kernel")
    parser.add_argument("kernel_recomp", help="file holding paths to files for recompiling to bc files")

    return parser

def main():
    arg_parser = setup_args()
    args = arg_parser.parse_args()
    
    kernel_path = args.kernel_dir
    kernel_conf = args.kernel_conf
    kernel_recomp = args.kernel_recomp

    """	
    	Attention: The initial compilation does not work for older Android kernels
        We compile the complete kernel with WLLVM once
        then we recompile all files under /drivers/ again to
        generate bitcode files
    """
    
    # change this if you want to use another build environment
    compile_env = get_env_kernel_wllvm()
    
    # this will compile the kernel with default config
    compile_kernel(kernel_path, kernel_conf, compile_env)
    
    # if we compiled with wllvm we can get the cmdline for each file
    # and recompile without optimization i.e. -O0
    # read here https://blog.xiexun.org/linux-bc-custom-opt.html
    search_old_commands_and_run_without_opt(kernel_path, kernel_recomp, compile_env)
    
if __name__ == '__main__':
    main()
    
    
