#!/usr/bin/env bash

QEMU_SERIAL_LOG=/out/qemu_serial.log
TARGET=${1:-intel-n5x}
HARNESS=${2:-noiface}
MMIO_FUZZ=${3:-nommio}
MMIO_FUZZ_LOG=${4:-0}
FUZZ_LOG=${5:-0}
# AFL++ UI during fuzzing on=1, off=0
FUZZ_UI=${6:-0}

# start receiver of QEMU's serial output in the background
cd /src/rehosting-framework/;
poetry run python boot-scripts/qemu-serial-receiver.py 2000 2002 >$QEMU_SERIAL_LOG 2>&1 &

# ensure that harness files are build
if [ ! -f "/src/manual-harness/generic_harness.so" ]; then
	cd /src/manual-harness/ && make
    echo "Manual harness files build in /src/manual-harness/"
fi

if [ ! -f "/in/$TARGET-bl31.bin" ]; then
	echo "Binary not found at /in/$TARGET-bl31.bin"
        exit -1
fi

# if there is no snapshot available take a new one
if [ ! -f "/out/snapshot.qcow2" ]; then
    cd /src/rehosting-framework/ && poetry run python boot-scripts/boot-$TARGET-secmon.py /in/$TARGET-bl31.bin --avatar-output-dir /out/ 
fi

# set iface harness if defined
if [ $HARNESS == "iface" ]; then
    export SMFUZZ_HARNESS_PATH="/src/manual-harness/synthesis_harness.so"
    if [ ! -f $SMFUZZ_HARNESSDATA_PATH ]; then
	    echo "No harnessdata found in $SMFUZZ_HARNESSDATA_PATH for $TARGET!"
	    echo "Run synthesis first!"
            exit -1
    fi
fi

# enable reflected peripheral modeling if defined by setting env variable
if [ $MMIO_FUZZ == "mmio" ]; then
    export SMFUZZ_MMIO_FUZZ="1"
fi
if [ $MMIO_FUZZ_LOG == 1 ]; then
    export SMFUZZ_MMIO_FUZZ_LOG="1"
fi
if [ $FUZZ_LOG == 1 ]; then
    export SMFUZZ_TRACE="1"
fi

# fire up the fuzzer
# ensure afl-in dir is not empty
mkdir -p /in/afl-in
echo "foo" > /in/afl-in/dummy

# set UI and DEBUG flags for AFL
if [ $FUZZ_UI == 0 ]; then
    export SMFUZZ_AFL_DEBUG="1"
    export SMFUZZ_AFL_NO_UI="1"
fi

cd /src

export SMFUZZ_AFL_OUT_DIR="/out/afl-out-$HARNESS-$MMIO_FUZZ"

python run_fuzzer.py $TARGET

chmod -R 777 /out;