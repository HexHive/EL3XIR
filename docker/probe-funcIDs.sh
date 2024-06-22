#!/usr/bin/env bash

QEMU_SERIAL_LOG=/out/qemu_serial.log
TARGET=${1:-intel-n5x}
START_FUNCID=${2:-0}
END_FUNCID=${3:-1000}

echo "Start: $START_FUNCID, End: $END_FUNCID"

cd /src/rehosting-framework/;
poetry run python boot-scripts/qemu-serial-receiver.py 2000 2002 >$QEMU_SERIAL_LOG 2>&1 &

# ensure that harness files are build
if [ ! -f "/src/manual-harness/probing_harness.so" ]; then
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

# use the probing harness that expects just a 32 bit value to set as funcID
export SMFUZZ_HARNESS_PATH="/src/manual-harness/probing_harness.so"

# use afl-showmap to only run once
export SMFUZZ_AFL_PATH="afl-showmap"

# define function identifier probing mode on
export AFL_FUNCID_PROBING=1

# create in directory for afl
mkdir -p /in/afl-probe-in/
export SMFUZZ_AFL_IN_DIR="/in/afl-probe-in/"

# write some dummy afl input testcase
echo "PROBING FUNCIDS" > /in/afl-probe-in/probing

# set out directory
export SMFUZZ_AFL_OUT_DIR="/out/afl-edges-probe-out/"

start_time=$(date +%s.%N)

export AFL_FUNCID_START=$START_FUNCID
export AFL_FUNCID_END=$END_FUNCID

cd /src && python run_fuzzer.py $TARGET;

end_time=$(date +%s.%N)
elapsed_time=$(echo "$end_time - $start_time" | bc)
printf "Elapsed time: %.2f seconds\n" $elapsed_time

chown -R 1000:1000 /out
chmod -R 777 /out/;
