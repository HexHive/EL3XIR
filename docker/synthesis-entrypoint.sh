#!/usr/bin/env bash

TARGET=${1:-intel-n5x}

# check if SVF smc-typerfinder tool available and compiled
if [ ! -f "/src/svf/Release-build/bin/smc_type_finder" ]; then
    cd /src/svf && ./build.sh
fi

export PATH=/src/svf/Release-build/bin:$PATH

cd /in/
if [ ! -f "/in/merged.bc" ]; then
    echo "merged.bc not found!"
    echo "run prepkernel first or provide a merged bitcode file!"
    exit -1
fi

smc_type_finder -model-arrays merged.bc
chmod 777 harnessdata.csv
