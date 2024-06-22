DOCKER := docker

CPUID ?= 0
TARGET ?= intel-n5x
OUT_DIR := $(shell pwd)/out/$(TARGET)
IN_DIR := $(shell pwd)/in/$(TARGET)
# qemu logging during fuzzing on=1, off=0
FUZZ_LOG ?= 0

# reflected peripheral modeling on=mmio, off=nommio
MMIO_FUZZ ?= nommio
MMIO_FUZZ_LOG ?= 0

# interface-unaware=noiface, interface-aware=iface
HARNESS ?= noiface
# define compile config if using source Linux kernel
# use defonfig for intel-n5x and nxp-imx8mq
# for xilinx-zynqmp use "xilinx_zynqmp_defconfig "
# for nvidia-t186 use "tegra_defconfig"
KERNEL_CONF ?= defconfig

# specific for Linux
# leave at least one core free
NCORES = $(shell echo $$((`grep -c ^processor /proc/cpuinfo`-2)))
NRUNS = $(shell seq 0 $(NCORES))

# for running two campaigns at once with the same number of cores
NRUNSA := $(shell seq 0 $(shell echo $$((($(NCORES) + 1) / 2 - 1))))
NRUNSB := $(shell seq $(shell echo $$(($(NCORES) / 2 + 1))) $(NCORES))

# for testing the probing phase
START_FUNCID_PROBE ?= 0
END_FUNCID_PROBE ?= 1000

.PHONY: build

help: ## Show this help
	@egrep -h '\s##\s' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

################################################ BUILDING ################################################

build: compose.yaml ## Build the Docker container(s)
	IN=./in $(DOCKER) compose build

build-fuzz: compose.yaml ## Build the Docker image
	$(DOCKER) compose build -- el3xir-runner

build-synthesis: compose.yaml ## Build the Docker image
	$(DOCKER) compose build -- el3xir-synthesis

################################################ TESTING ################################################

run-fuzz-sh: ## Run the fuzzer Docker container and spawn a shell
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm \
		el3xir-runner /sh-entrypoint.sh

run-fuzz-test: ## Run the fuzzer Docker container with a single target and on one core
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	CPUSET=$(CPUID) \
	$(DOCKER) compose run --rm \
		el3xir-runner /fuzzer-entrypoint.sh $(TARGET) $(HARNESS) $(MMIO_FUZZ) $(MMIO_FUZZ_LOG) $(FUZZ_LOG) 1

run-cov-single: ## Run found inputs again with logging active generate bitmaps for cov over time
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR)/ \
	$(DOCKER) compose run --rm \
		el3xir-runner /rerun-testcases.sh $(TARGET) all $(HARNESS) $(MMIO_FUZZ) $(MMIO_FUZZ_LOG) 1; \
	mv $(OUT_DIR)/qemu-fuzzing-logging.log $(OUT_DIR)/cov.log

run-synth-sh: ## Run the harness synthesis Docker container and spawn a shell
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm \
		el3xir-synthesis /sh-entrypoint.sh

run-prepkernel: ## Run the synthesis Docker container to compile kernel
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm \
		el3xir-synthesis /prepkernel-entrypoint.sh $(TARGET) $(KERNEL_CONF)

run-synthesis: ## Run the synthesis Docker container for interface recovery
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm \
		el3xir-synthesis /synthesis-entrypoint.sh $(TARGET)

run-probe: ## Probe all funcIDs defined in the SMC Calling Convention and prune harness
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm el3xir-runner chmod -R 777 /out; \
	cp $(IN_DIR)/harnessdata.csv $(IN_DIR)/harnessdata-noProbe.csv
	src/probe-smccc.py $(TARGET) $(NCORES) $(IN_DIR) $(OUT_DIR)

run-cov-plot:
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm \
		el3xir-runner /cov-plot-entrypoint.sh $(TARGET) $(HARNESS) $(MMIO_FUZZ)

################################################ EVALUATION ################################################

run-fuzz-eval:
	$(foreach i, \
	  $(NRUNS), \
	  echo "STARTING INSTANCE $(i)"; \
	  IN=$(IN_DIR) \
	  OUT=$(OUT_DIR)/$(i) \
	  CPUSET=$(i) \
	  $(DOCKER) compose run --name el3xir-$(i) -d --rm \
	  	el3xir-runner /fuzzer-entrypoint.sh $(TARGET) $(HARNESS) $(MMIO_FUZZ) $(MMIO_FUZZ_LOG) $(FUZZ_LOG) 0 \
	 )

run-fuzz-comp-eval:
	$(foreach i, \
	  $(NRUNSA), \
	  echo "STARTING INSTANCE $(i)"; \
	  IN=$(IN_DIR) \
	  OUT=$(OUT_DIR)/$(i) \
	  CPUSET=$(i) \
	  $(DOCKER) compose run --name el3xir-$(i) -d --rm \
	  	el3xir-runner /fuzzer-entrypoint.sh $(TARGET) iface mmio $(MMIO_FUZZ_LOG) $(FUZZ_LOG) 0 \
	 )
	$(foreach i, \
	  $(NRUNSB), \
	  echo "STARTING INSTANCE $(i)"; \
	  IN=$(IN_DIR) \
	  OUT=$(OUT_DIR)/$(i) \
	  CPUSET=$(i) \
	  $(DOCKER) compose run --name el3xir-$(i) -d --rm \
	  	el3xir-runner /fuzzer-entrypoint.sh $(TARGET) noiface nommio $(MMIO_FUZZ_LOG) $(FUZZ_LOG) 0 \
	 )

run-cov-eval: ## Run all found inputs again with logging active generating bitmaps for cov over time
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm el3xir-runner chmod -R 777 /out; \
	rm -f "$(OUT_DIR)/cov-logs-$(HARNESS)-$(MMIO_FUZZ).log"; \
	mkdir -p $(OUT_DIR)/queues-$(HARNESS)-$(MMIO_FUZZ); \
	$(foreach i, \
	  $(NRUNS), \
	  echo "COLLECTING INSTANCE $(i)"; \
	  IN=$(IN_DIR) \
	  OUT=$(OUT_DIR)/$(i)/ \
	  $(DOCKER) compose run --rm \
		el3xir-runner /rerun-testcases.sh $(TARGET) all $(HARNESS) $(MMIO_FUZZ) $(MMIO_FUZZ_LOG) 1; \
	  mv $(OUT_DIR)/$(i)/afl-out-$(HARNESS)-$(MMIO_FUZZ)-edges-all $(OUT_DIR)/queues-$(HARNESS)-$(MMIO_FUZZ)/queue-$(i); \
	  cat $(OUT_DIR)/$(i)/qemu-fuzzing-logging.log >> "$(OUT_DIR)/cov-logs-$(HARNESS)-$(MMIO_FUZZ).log"; \
	 )

run-cov-comp-eval:
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm el3xir-runner chmod -R 777 /out; \
	rm -f "$(OUT_DIR)/cov-logs-iface-mmio.log"; \
	mkdir -p $(OUT_DIR)/queues-iface-mmio; \
	$(foreach i, \
	  $(NRUNSA), \
	  echo "COLLECTING INSTANCE $(i)"; \
	  IN=$(IN_DIR) \
	  OUT=$(OUT_DIR)/$(i)/ \
	  $(DOCKER) compose run --rm \
		el3xir-runner /rerun-testcases.sh $(TARGET) all iface mmio $(MMIO_FUZZ_LOG) 1; \
	  mv $(OUT_DIR)/$(i)/afl-out-iface-mmio-edges-all $(OUT_DIR)/queues-iface-mmio/queue-$(i); \
	  cat $(OUT_DIR)/$(i)/qemu-fuzzing-logging.log >> "$(OUT_DIR)/cov-logs-iface-mmio.log"; \
	 )
	rm -f "$(OUT_DIR)/cov-logs-noiface-nommio.log"; \
	mkdir -p $(OUT_DIR)/queues-noiface-nommio; \
	$(foreach i, \
	  $(NRUNSB), \
	  echo "COLLECTING INSTANCE $(i)"; \
	  IN=$(IN_DIR) \
	  OUT=$(OUT_DIR)/$(i)/ \
	  $(DOCKER) compose run --rm \
		el3xir-runner /rerun-testcases.sh $(TARGET) all noiface nommio $(MMIO_FUZZ_LOG) 1; \
	  mv $(OUT_DIR)/$(i)/afl-out-noiface-nommio-edges-all $(OUT_DIR)/queues-noiface-nommio/queue-$(i); \
	  cat $(OUT_DIR)/$(i)/qemu-fuzzing-logging.log >> "$(OUT_DIR)/cov-logs-noiface-nommio.log"; \
	 )

# Run the complete harness synthesis eval pipeline - see summary of results in /out/$TARGET/synth-summary-<targetname>.txt
run-synth-eval: run-prepkernel run-synthesis run-probe

run-mmio-eval:
	rm -f "$(OUT_DIR)/mmio-logs-$(HARNESS)-$(MMIO_FUZZ).log"; \
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm el3xir-runner chmod -R 777 /out; \
	$(foreach i, \
	  $(NRUNS), \
	  echo "COLLECTING INSTANCE $(i)"; \
	  IN=$(IN_DIR) \
	  OUT=$(OUT_DIR)/$(i)/ \
	  $(DOCKER) compose run --rm \
		el3xir-runner /rerun-testcases.sh $(TARGET) all $(HARNESS) $(MMIO_FUZZ) 1 1; \
	  cat $(OUT_DIR)/$(i)/qemu-fuzzing-logging.log >> "$(OUT_DIR)/mmio-logs-$(HARNESS)-$(MMIO_FUZZ).log"; \
	 )
	 src/count_mmio.py $(TARGET) $(OUT_DIR)/mmio-logs-$(HARNESS)-$(MMIO_FUZZ).log > $(OUT_DIR)/mmio-summary-$(TARGET)-$(HARNESS)-$(MMIO_FUZZ).txt;

## Run found crashes for all N instances again, collect logfile, dedup crashes - seee summary of results in /out/$TARGET/crash-summary-<targetname>-<harness>-<mmio>.txt
run-dedup-crashes: 
	rm -f "$(OUT_DIR)/crash-logs-$(HARNESS)-$(MMIO_FUZZ).log"; \
	$(foreach i, \
	  $(NRUNS), \
	  echo "COLLECTING INSTANCE $(i)"; \
	  IN=$(IN_DIR) \
	  OUT=$(OUT_DIR)/$(i)/ \
	  $(DOCKER) compose run --rm \
	  	el3xir-runner /rerun-testcases.sh $(TARGET) crashes $(HARNESS) $(MMIO_FUZZ) $(MMIO_FUZZ_LOG) 1; \
	  IN=$(IN_DIR) \
	  OUT=$(OUT_DIR)/ \
	  $(DOCKER) compose run --rm el3xir-runner chmod -R 777 /out; \
	  cat $(OUT_DIR)/$(i)/qemu-fuzzing-logging.log >> "$(OUT_DIR)/crash-logs-$(HARNESS)-$(MMIO_FUZZ).log"; \
	 )
	 src/dedup-crashes.py $(OUT_DIR)/crash-logs-$(HARNESS)-$(MMIO_FUZZ).log > $(OUT_DIR)/crash-summary-$(TARGET)-$(HARNESS)-$(MMIO_FUZZ).txt;

run-cov-comp-plot:
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm \
		el3xir-runner /cov-plot-entrypoint.sh $(TARGET) iface mmio
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm \
		el3xir-runner /cov-plot-entrypoint.sh $(TARGET) noiface nommio

################################################ HELPER ################################################

run-mmio-comp-eval:
	rm -f "$(OUT_DIR)/mmio-logs-iface-mmio.log"; \
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	$(DOCKER) compose run --rm el3xir-runner chmod -R 777 /out; \
	$(foreach i, \
	  $(NRUNSA), \
	  echo "COLLECTING INSTANCE $(i)"; \
	  IN=$(IN_DIR) \
	  OUT=$(OUT_DIR)/$(i)/ \
	  $(DOCKER) compose run --rm \
		el3xir-runner /rerun-testcases.sh $(TARGET) all iface mmio 1 1; \
	  cat $(OUT_DIR)/$(i)/qemu-fuzzing-logging.log >> "$(OUT_DIR)/mmio-logs-iface-mmio.log"; \
	 )
	 src/count_mmio.py $(TARGET) $(OUT_DIR)/mmio-logs-iface-mmio.log > $(OUT_DIR)/mmio-summary-$(TARGET)-iface-mmio.txt;


run-probe-single: ## Run the fuzzer container and probe defined funcIDs, if longer probes also use -d
	IN=$(IN_DIR) \
	OUT=$(OUT_DIR) \
	CPUSET=$(CPUID) \
	$(DOCKER) compose run --name el3xir-probe-$(CPUID) --rm \
		el3xir-runner /probe-funcIDs.sh $(TARGET) $(START_FUNCID_PROBE) $(END_FUNCID_PROBE)

halt:
	$(foreach i, \
	  $(NRUNS), \
	  echo "STOPPING INSTANCE $(i)"; \
	  $(DOCKER) exec el3xir-$(i) chmod -R 777 /out; \
	  $(DOCKER) stop el3xir-$(i) & \
	 )

