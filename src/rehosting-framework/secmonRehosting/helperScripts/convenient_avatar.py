from typing import List

from avatar2 import Avatar, QemuTarget

from . import InMemoryBufferPeripheral


class ConvenientAvatar(Avatar):
    """
    Provides additional methods which e.g., add specific types of devices with sane defaults.
    Used in avatar2 based scripts.
    """

    def add_pl011(self, address: int, size: int, name: str, value: int):
        properties = {"type": "serial", "value": value, "name": "chardev"}

        return self.add_memory_range(address, size, name=name, qemu_name="pl011", qemu_properties=properties)

    def add_arm_gic_v2(self):
        # when adding any memory section with the name gic*, the configurable machine will create a GIC v2 device and
        # wire it up to the main CPU
        self.add_memory_range(0x8000000, 0x10000, name="gic_dist")
        self.add_memory_range(0x8010000, 0x10000, name="gic_cpu")

    def add_qemu_target(
        self, entry_address: int, enable_semihosting: bool = True, additional_args: List[str] = None
    ) -> QemuTarget:
        # connect serial outputs to the QEMU serial receiver script

        if additional_args is None:
            additional_args = []

        additional_args += [
            "-serial",
            "tcp:localhost:2000",
            "-serial",
            "tcp:localhost:2002",
        ]

        if enable_semihosting:
            # enable semihosting, which is utilized by the standard OP-TEE QEMUv8 boot chain
            # it doesn't really do any harm when you're not using it either
            additional_args += [
                "-semihosting-config",
                "enable,target=native",
            ]

        # note: this will return not a Target but a ConvenientQemuTarget, so please ignore the IDE's warning
        return self.add_target(
            QemuTarget, name="qemu", gdb_port=1235, additional_args=additional_args, entry_address=entry_address
        )

    def add_in_memory_buffer_peripheral(
        self, address: int, size: int, name: str = None, permissions: str = None, data: bytes = None
    ):
        # avoid passing None as a value for keyword args if no value was specified
        # this avoids overwriting potential non-None keyword argument default values
        # these are used heavily in avatar2, despite this being an anti-pattern in Python
        extra_args = dict()

        if permissions is not None:
            extra_args["permissions"] = permissions

        if name is not None:
            extra_args["name"] = name

        mem_range = self.add_memory_range(address, size, emulate=InMemoryBufferPeripheral, **extra_args)

        # DbC: check invariant
        assert mem_range.forwarded

        if data is not None:
            # convenience feature: write data directly into the buffer
            # this way, the caller doesn't have to fiddle with forwarded_to
            peripheral: InMemoryBufferPeripheral = mem_range.forwarded_to
            peripheral.write_into_buffer(data)

        return mem_range
