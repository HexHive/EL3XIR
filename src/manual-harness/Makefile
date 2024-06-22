QEMU_BASE ?= ../aflvatarplusplus/qemu_mode/
INCLUDE := -I$(QEMU_BASE)/qemuafl/include -I$(QEMU_BASE)/qemuafl

all:
	$(CC) $(INCLUDE) -fPIC -shared generic_harness.c -o generic_harness.so
	$(CC) $(INCLUDE) -fPIC -shared synthesis_harness.c -o synthesis_harness.so
	$(CC) $(INCLUDE) -fPIC -shared probing_harness.c -o probing_harness.so

clean:
	rm -rf generic_harness.so
	rm -rf synthesis_harness.so
	rm -rf probing_harness.so
