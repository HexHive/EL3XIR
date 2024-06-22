#!/usr/bin/env bash

TARGET=${1:-intel-n5x}
HARNESS=${2:-noiface}
MMIO_FUZZ=${3:-nommio}

TARGET=${TARGET//-/}

# collect edges and write to csv
cd /out/ && python /src/plotting/aggregate.py queues-$HARNESS-$MMIO_FUZZ/ 0-$HARNESS$MMIO_FUZZ-$TARGET.csv

# plot graphs
cd /out/ && python /src/plotting/covplot.py 0-*

chown -R 1000:1000 /out
chmod -R 777 /out/;
