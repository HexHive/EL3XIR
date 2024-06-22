# EL3XIR

EL3XIR is a framework that enables rehosting and effectively fuzzing COTS secure monitor implementations. Please see our USENIX Security'24 paper for more details: [EL3XIR: Fuzzing COTS Secure Monitors](https://www.usenix.org/conference/usenixsecurity24/presentation/lindenmeier).

## Requirements
We tested EL3XIR on Ubuntu 22.04.
You need `git` to download associated repositories. We tested `git version 2.34.1`, but newer versions will likely work as well.
```
apt install git
```

Install the [docker engine](https://docs.docker.com/engine/install/ubuntu/).
We tested `Docker version 26.1.3, build b72abbb`.
We are using the `compose` plugin to create and run containers (tested `Docker Compose version v2.27.1`).
```
apt install docker-compose-plugin
```
If you have problems with docker compose make sure you installed it according to https://github.com/docker/compose/tree/v2#linux.

You will also need Python. We tested `version 3.10.12`.

Download this repos and its submodules:
```bash
git clone --recursive git@github.com:HexHive/EL3XIR.git
cd EL3XIR

# Troubleshooting: update the qemuafl submodule if not present yet
cd src/aflvatarplusplus
git submodule update --init -- qemu_mode/qemuafl

# if other submodules are not present, act similar
```

## Building with Docker
We recommend building EL3XIR using our Dockerfile at `docker\Dockerfile`.
We provide a `Makefile` that helps to build EL3XIR and reproduce results.
You can run `make build` to start the build process.
This will build docker images `el3xir` (for rehosting and fuzzing) and `el3xir-synthesis` (for static harness synthesis).

If successful, you can execute `make run-fuzz-sh` or `make run-synth-sh` to run the corresponding container and spawn a shell.

## Directory Structure
We follow some conventions for locations.

| Path | Description |
| :--- | :--- |
| `/docker` | EL3XIR Dockerfile and docker entrypoints |
| `/in` | EL3XIR expects target binaries, kernel source, and configs here. The synthesized harness file will also be placed here. |
| `/out` | EL3XIR will place results here. For each target there will be a folder `$TARGET`. You may delete the target folder to start fresh fuzzing campaigns. |
| `/src` | EL3XIR source code and scripts |
| `/src/aflvatarplusplus` | Source code of our AFL++ fork |
| `/src/aflvatarplusplus/qemu_mode/qemuafl` | Source code of our qemuafl fork supporting avatar2's configurable machine with full system emulation |
| `/src/avatar2` | Source code of our avatar2 fork supporting aarch64 |
| `/src/rehosting-framework` | Source code of EL3XIR's rehosting framework using avatar2 |
| `/src/manual-harness` | Source code and binaries of manually developed harnesses for EL3XIR (generic, probing, and synthesis that must be refined with harnessdata)|
| `/src/plotting` | Python scripts for plotting coverage results |
| `/src/svf` | Source code of our SVF fork including EL3XIR's smc-type-finder module for harness synthesis |

## Artifacts
Please download artifact at: `https://zenodo.org/records/12250146`.
Depending on the configuration, you will require multiple input artifacts that should all be place in `/in/$TARGET`, i.e., a new folder for every new target.
For naming we encourage the convention `vendor-soc`.
When running EL3XIR without interface awareness (noiface) and reflected peripheral modeling (mmio or nommio), we only require the target secure monitor binary at `/in/$TARGET/vendor-soc-bl31.bin`.
When including EL3XIR's harness synthesis (iface), we also require the corresponding source code of the (Linux) kernel for the target SoC at `/in/$TARGET/kernel/`.
Alternatively, you may use compiled LLVM-Bitcode of the target kernel. 
We skip the compiling process if we find a file named `llvm_generate_preprocessed.sh` in the kernel folder.
For harness synthesis from a merged kernel bitcode file, we require the file `/in/$TARGET/llvm-link.lst` that defines each kernel object file to include for interface recovery.
The file `llvm-link.lst` must hold the name of each kernel object file in the format `filename.noopt.bc`.

## Usage
After successfull compilation, you can use EL3XIR via the make targets defined in `Makefile`.
Here, we provide a quick overview of the most interesting targets.
For further documentation about parameters look into the Makefile.

### Simple Test
For running a simple single-core fuzzing campaign, place a targeted secure monitor binary at `/in/$TARGET/vendor-soc-bl31.bin`.
Then execute `make run-fuzz-test`.
This will (1) boot the secure monitor in its rehosting environment, (2) take a snapshot, and (3) start EL3XIR's fuzzer and show AFL++'s dashboard when successfull.
Subsequent runs will directly start the fuzzer when a snapshot is found at `/out/$TARGET/snapshot.qcow2`.
Fuzzing outputs can be found at `/out/$TARGET/afl-out-$HARNESS-$MMIO_FUZZ/` (for the default test `HARNESS=noiface` and `MMIO_FUZZ=nommio`).

### Harness Synthesis
For EL3XIR's harness synthesis we require the source code (or LLVM-Bitcode) of the kernel running in the normal world of the SoC at `/in/$TARGET/kernel/`.
Furthermore, we require a definition of hand-picked kernel objectfiles in `llvm-link.lst` to generate a merged partition.
Then execute `make run-synth-eval`.
This will (1) compile the Linux kernel and link the partition, (2) perform static analysis for interface recovery, and (3) run the function identifier probing phase.
Note that (1) and (3) may take multiple minutes.
The following output files should be found when successful:

| Path | Description |
| :--- | :--- |
| `/in/$TARGET/merged.bc` | The merged LLVM-Bitcode partition consisting of kernel object files defined in `llvm-link.lst`. |
| `/in/$TARGET/harnessdata-noProbe.csv` | A backup of the harnessdata after static analysis but without probing. |
| `/in/$TARGET/harnessdata.csv` | The final synthezied harnessdata used for interface-aware fuzzing. |
| `/out/$TARGET/synth-summary-$TARGET.txt` | A summarized report about the results of the probing phase and the static interface recovery. |

### Multi-core Fuzzing
EL3XIR can be configured to run with/without interface-awareness (iface) and/or reflected peripheral modeling (mmio).
For running with interface-awareness ensure to synthesize the harness first.
Execute `make run-fuzz-eval $TARGET $HARNESS $MMIO_FUZZ` to start multiple fuzzing campaigns at once, each on its own docker container (`el3xir-$(i)`) and own core.
EL3XIR will automatically detect the number of available cores (`NCORES`) and start NCORES-1 campaigns (you may adjust the Makefile if necessary).
When running EL3XIR's baseline set `$HARNESS=noiface` and `$MMIO_FUZZ=nommio`.
For the full configuration set `$HARNESS=iface` and `$MMIO_FUZZ=mmio`.
You may also enable only one option individually.
Fuzzing campaigns will run for 24 hours per default (change `-V 86400` in `run_fuzzer.py` if necessary).
You can also halt all containers by running `make halt`.
For directly comparing EL3XIR's full configuration (iface/mmio) to its baseline (noiface/nommio) you can run `make run-fuzz-comp-eval $TARGET`.

The following output files should be found when successful:

| Path | Description |
| :--- | :--- |
| `/out/$TARGET/$(i)` | For every campaign there exists a standalone folder ranging from `0` to `NCORES-2`. |
| `/out/$TARGET/$(i)/afl-out-$HARNESS-$MMIO_FUZZ/` | Similar to the content found when running a standalone fuzzing test. See AFL++ directory structure. An overview of the fuzzer stats can be found at `default/fuzzer_stats`.|

### Evaluation
After a fuzzing campaign, EL3XIR has multiple make targets to evaluate the output (e.g., crashes, coverage, reflected peripheral modeling).

#### Edge Coverage
You can run `make run-cov-eval $TARGET $HARNESS $MMIO_FUZZ` to rerun all inputs found by a previous fuzzing campaign with increased logging.
Note that after long runs, logging files can be multiple GBs.
When previously using `make run-fuzz-comp-eval $TARGET` you should use `make run-cov-comp-eval $TARGET` that reruns both campaigns.
The following output files should be found when successful:

| Path | Description |
| :--- | :--- |
| `/out/$TARGET/cov-logs-$HARNESS-$MMIO_FUZZ.log` | Combined logging of all rerun test cases. |
| `/out/$TARGET/queues-$HARNESS-$MMIO_FUZZ/` | Includes folder names `queue-0` that hold the edge coverage information for each rerun fuzzing test case. |

You may also plot an edge coverage graph by running `make run-cov-plot $TARGET $HARNESS $MMIO_FUZZ`.
When previously using `make run-cov-comp-eval $TARGET` you should use `make run-cov-comp-plot $TARGET` that automatically includes both previously run campaigns in the plot.
The following output files should be found when successful:

| Path | Description |
| :--- | :--- |
| `/out/$TARGET/0-$HARNESS$MMIO_FUZZ-$TARGET.csv` | Aggregated coverage data over all runs, excluding duplicates. |
| `/out/$TARGET/plot.pdf` | Visual graph of coverage over time including min, max, and avg. |

Note that the coverage graph will include all aggregated data in files named `0-*` and sort them by target and method.

#### Crash Deduplication and Summary
For crash triaging you can rerun found crash inputs and deduplicate them according to their execution profile.
Note that there is still manual inspection necessary for improved deduplication.
Execute `make run-dedup-crashes $TARGET $HARNESS $MMIO_FUZZ` to rerun all crash test cases and generate a summary.
The following output files should be found when successful:

| Path | Description |
| :--- | :--- |
| `/out/$TARGET/crash-logs-$HARNESS-$MMIO_FUZZ.log` | Combined logging of all crash inputs found. |
| `/out/$TARGET/crash-summary-$TARGET-$HARNESS-$MMIO_FUZZ.txt` | Summary of deduplicated crashes. For every test case it provides the raw input data and an execution trace. |

#### Reflected Peripheral Modeling
For evaluating the effectiveness of EL3XIR's reflected peripheral modeling, you can run `run-mmio-eval $TARGET $HARNESS $MMIO_FUZZ`.
This will rerun all found test cases with increased MMIO logging active and provide a summary.
The following output files should be found when successful:

| Path | Description |
| :--- | :--- |
| `/out/$TARGET/mmio-logs-$HARNESS-$MMIO_FUZZ.log` | Combined logging of all rerun test cases with MMIO read logging. You may search for `MMIO fuzz read` to find entries manually. |
| `/out/$TARGET/mmio-summary-$TARGET-$HARNESS-$MMIO_FUZZ.txt` | Summary of modeled MMIO registers, values, and affected runtime services. |