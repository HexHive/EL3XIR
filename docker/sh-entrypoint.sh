#!/usr/bin/env bash

QEMU_SERIAL_LOG=/out/qemu_serial.log

# start receiver of QEMU's serial output in the background
cd /src/rehosting-framework/;
poetry run python boot-scripts/qemu-serial-receiver.py 2000 2002 >$QEMU_SERIAL_LOG 2>&1 &

# ensure that harness files are build
if [ ! -f "/src/manual-harness/generic_harness.so" ]; then
	cd /src/manual-harness/ && make
    echo "Manual harness files build in /src/manual-harness/"
fi

/bin/bash
chown -R 1000:1000 /out
chmod -R 777 /out/;
