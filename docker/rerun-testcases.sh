#!/usr/bin/env bash

QEMU_SERIAL_LOG=/out/qemu_serial.log
TARGET=${1:-intel-n5x}
SUBDIR=${2:-queue}
HARNESS=${3:-noiface}
MMIO_FUZZ=${4:-nommio}
MMIO_FUZZ_LOG=${5:-0}
FUZZ_LOG=${6:-1}

cd /src/rehosting-framework/;
poetry run python boot-scripts/qemu-serial-receiver.py 2000 2002 >$QEMU_SERIAL_LOG 2>&1 &

# concate expected path depending on config
export SMFUZZ_AFL_RERUN_DIR="/out/afl-out-$HARNESS-$MMIO_FUZZ"

if [ ! -f "$SMFUZZ_AFL_RERUN_DIR/default/fuzzer_setup" ]; then
    echo "No fuzzing run found for $TARGET with $HARNESS and $MMIO_FUZZ..."
    echo "Run fuzzer first!"
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

export SMFUZZ_AFL_IN_DIR="$SMFUZZ_AFL_RERUN_DIR/default/$SUBDIR/"
if [ $SUBDIR == "crashes" ]; then    
    cd $SMFUZZ_AFL_RERUN_DIR/default/crashes/ && rm -f README.txt;
    export SMFUZZ_PRINT_TESTCASES="1";
fi
if [ $SUBDIR == "all" ]; then
    mkdir -p /out/afl-rerun/
    cd $SMFUZZ_AFL_RERUN_DIR/default/crashes/ && rm -f README.txt;
    cp -a $SMFUZZ_AFL_RERUN_DIR/default/queue/. /out/afl-rerun/.;
    cp -a $SMFUZZ_AFL_RERUN_DIR/default/crashes/. /out/afl-rerun/.;
    cp -a $SMFUZZ_AFL_RERUN_DIR/default/hangs/. /out/afl-rerun/.;
    export SMFUZZ_AFL_IN_DIR="/out/afl-rerun/";
fi

export SMFUZZ_AFL_OUT_DIR="$SMFUZZ_AFL_RERUN_DIR-edges-$SUBDIR/"

export SMFUZZ_AFL_PATH="afl-showmap"

# enable reflected peripheral modeling (=set env) if defined
if [ $MMIO_FUZZ == "mmio" ]; then
    export SMFUZZ_MMIO_FUZZ="1"
fi
if [ $MMIO_FUZZ_LOG == 1 ]; then
    export SMFUZZ_MMIO_FUZZ_LOG="1"
fi
if [ $FUZZ_LOG == 1 ]; then
    export SMFUZZ_TRACE="1"
fi

# disable UI for reruns
export SMFUZZ_AFL_DEBUG="1"
export SMFUZZ_AFL_NO_UI="1"

cd /src && python run_fuzzer.py $TARGET;

chmod -R 777 /out;