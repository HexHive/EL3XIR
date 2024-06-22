import re

from avatar2 import Target, TargetStates


class TargetBridge:
    """
    Allows modifying requests to and replies from Avatar targets. Decouples Avatar2 targets and our implementations.

    Introducing one level of abstraction allows us to patch requests, which is required when working with both
    "real" AArch32 targets as well as an AArch64 target that run in svc32/usr32 mode and use our custom GDB stub.
    The implementation of the error interpreter does not need to do the differentiation between the cases.
    """

    def read_register(self, name: str):
        raise NotImplementedError()

    def write_register(self, name: str, value: int):
        raise NotImplementedError()

    def read_memory(self, address: int, size: int, num_words: int = 1, raw: bool = False):
        raise NotImplementedError()

    def write_memory(self, address: int, size: int, value: int, num_words: int = 1, raw: bool = False):
        raise NotImplementedError()


class TargetBridgeBase(TargetBridge):
    """
    Abstract base class. Contains code common to all implementations.

    The class implements a few sanity checks as well in order to recognize invalid conditions, e.g., when the target
    exits unexpectedly.
    """

    def __init__(self, target: Target):
        self._target = target

    def _check_class_invariants(self):
        assert self._target.state != TargetStates.EXITED, "target exited unexpectedly"

    def _make_class_invariants_checker(self):
        # to check class invariants more conveniently, a context manager can be used with the with statement

        parent_self = self

        class ClassInvariantsChecker:
            def __enter__(self):
                parent_self._check_class_invariants()

            def __exit__(self, exc_type, exc_val, exc_tb):
                parent_self._check_class_invariants()

        return ClassInvariantsChecker()

    def _translate_register_name(self, name: str) -> str:
        raise NotImplementedError()

    def _translate_memory_address(self, address: int) -> int:
        raise NotImplementedError()

    def read_register(self, name: str):
        with self._make_class_invariants_checker():
            name = self._translate_register_name(name)
            return self._target.read_register(name)

    def write_register(self, name: str, value: int):
        with self._make_class_invariants_checker():
            name = self._translate_register_name(name)
            return self._target.write_register(name, value)

    def read_memory(self, address: int, size: int, num_words: int = 1, raw: bool = False):
        with self._make_class_invariants_checker():
            address = self._translate_memory_address(address)
            return self._target.read_memory(address, size, num_words=num_words, raw=raw)

    def write_memory(self, address: int, size: int, value: int, num_words: int = 1, raw: bool = False):
        with self._make_class_invariants_checker():
            address = self._translate_memory_address(address)
            return self._target.write_memory(address, size, value, num_words=num_words, raw=raw)


class DefaultTargetBridge(TargetBridgeBase):
    """
    Default implementation that just forwards all requests without patching them.
    """

    def _translate_memory_address(self, address: int) -> int:
        return address

    def _translate_register_name(self, name: str) -> str:
        return name


class AArch64Compat32TargetBridge(DefaultTargetBridge):
    """
    Implementation that patches requests before forwarding them to the QEMU target, and narrows received values to
    a size of 32-bit.
    """

    def _translate_register_name(self, name: str):
        name = name.lower()

        # support 32-bit register names
        match = re.match(r"^r(\d+)", name)
        if match:
            name = f"x{match.group(1)}"

        if name == "lr":
            name = "x14"

        if name == "dfsr":
            # the lower 32 bits of the ESR_EL1 register sent to us by the GDB stub contain the DFSR register
            # excerpt from AArch64 manual:
            # ESR_EL1 bits [31:0] are architecturally mapped to AArch32 System register DFSR[31:0]
            name = "ESR_EL1"

        return name

    def read_register(self, name: str):
        # truncate value to 32-bit if necessary
        return super().read_register(self._translate_register_name(name)) & 0xFFFFFFFF

    def write_register(self, name: str, value: int):
        # truncate value to 32-bit if necessary
        return super().write_register(self._translate_register_name(name), value & 0xFFFFFFFF)
