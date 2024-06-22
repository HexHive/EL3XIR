#!/usr/bin/env bash

TARGET=${1:-intel-n5x}
KERNEL_CONF=${2:-defconfig}
KERNEL_RECOMP=${3:-llvm-link.lst}

# check if already LLVM-bitcode files
if [ -f "/in/kernel/llvm_generate_preprocessed.sh" ]; then
    echo "Bitcode files detected, skipping compile..."
    cd /in/kernel/
    llvm-link `cat /in/llvm-link.lst` -o /in/merged.bc
    echo "/in/merged.bc generated"
    exit 0
fi

# check if LLVM / Clang is available and compiled
if [ ! -f "/src/svf/llvm-14.0.0.obj/bin/clang" ]; then
    cd /src/svf && ./build.sh
fi

export PATH=/src/svf/llvm-14.0.0.obj/bin:$PATH

echo "Compiling $TARGET kernel with $KERNEL_CONF config"

if [ ! -f "/in/kernel/vmlinux" ]; then
    cd /src/ && python compile_and_get_bc.py /in/kernel/ $KERNEL_CONF /in/$KERNEL_RECOMP
    cd /in/kernel/
    llvm-link `cat /in/llvm-link.lst` -o /in/merged.bc
    echo "/in/merged.bc generated"
else
    echo "Kernel already compiled!"
    exit 0
fi
