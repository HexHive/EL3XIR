# EL3XIR's Secure Monitor Rehosting Framework

EL3XIR's secure monitor rehosting framework is a Python library that makes rehosting proprietary secure monitor binaries easy.
It is implemented on top of [avatar2](https://github.com/avatartwo/avatar2).
This project is part of EL3XIR, an end-to-end fuzzing solution for COTS secure monitor implementations.
Please see our USENIX Security'24 paper for more details: [EL3XIR: Fuzzing COTS Secure Monitors](https://www.usenix.org/conference/usenixsecurity24/presentation/lindenmeier).

This rehosting framework focuses on rehosting ARM TrustZone TEE firmware, specifically the secure monitor firmware running at the highest privileged exception level EL3.

## Directory Structure

| Path | Description |
| :--- | :--- |
| `/boot-scripts` | Scripts to boot up rehosted targets in their environment  |
| `/secmonRehosting` | Core of the framework including helper scripts and rehosting environments |
| `/secmonRehosting/helper-scripts` | Useful scripts during manual rehosting |
| `/secmonRehosting/rehosting-environments` | Implementations of rehosting environments for secure monitor binary targets |

## Docker Setup
This project is part of the secure monitor fuzzing framework EL3XIR, we recommend using its Dockerfile to setup the rehosting framework.

## Running rehosted Secure Monitors
To run a rehosted secure monitor binary in its rehosting environment just execute the corresponding boot script with this command:
```bash
# here you should find or place a boot script
cd boot-scripts

# run the boot script with poetry
# specify the path to the binary and the path to the output folder
poetry run python boot-$TARGET-secmon.py ../in-binaries/$TARGET-bl31.bin --avatar-output-dir ../out/

# the process is successful if the secure monitor is booted up until the point when switching to the normal world
# the provided boot scripts will take a snapshot of the booted secure monitor
```
When adding a new secure monitor, you need to provide a boot script and a rehosting environment in `secmonRehosting/rehostingEnvironments`.