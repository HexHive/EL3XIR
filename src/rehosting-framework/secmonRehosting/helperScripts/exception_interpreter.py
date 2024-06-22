from .. import get_logger
from .target_bridge import TargetBridge


class AArch32ExceptionInterpreter:
    """
    Interpreter for AArch32 exceptions described in the ARMv7 manual.

    In AArch32, the type of the exception cannot be read from a register, as it would be possible in AArch64. Instead,
    a so-called exception vector table is used to dispatch exceptions to OS-provided handlers.
    In TrustedCore, for instance, the vector table is a list of branch instructions that call the appropriate handlers.

    This class offers handlers for all OS-handled exceptions. An Avatar2 script shall place breakpoints inside the
    vector table and call the appropriate handler. The handler then fetches all the available information and logs the
    results in a human-friendly way.
    """

    def __init__(self, target_bridge: TargetBridge):
        # dependency injection
        self._target_bridge = target_bridge

        self._logger = get_logger("aarch32_error_interpreter")

    def handle_reset(self):
        # has not been needed yet
        raise NotImplementedError()

    def handle_FIQ(self):
        # has not been needed yet
        raise NotImplementedError()

    def handle_IRQ(self):
        # has not been needed yet
        raise NotImplementedError()

    def handle_prefetch_abort(self):
        # happens on the first SVC performed in the 32-bit emulator
        # interesting documentation:
        # https://community.cypress.com/t5/Knowledge-Base-Articles/Troubleshooting-Guide-for-Arm-Abort-Exceptions-in-Traveo-I-MCUs/ta-p/248577
        # the abort address is contained in lr aka r14
        # note that the TC handler in 0xc001f69c subs 0x4, so we do the same
        abort_address = self._target_bridge.read_register("lr") - 0x4
        self._logger.error(f"prefetch abort exception in {hex(abort_address)}")

    def handle_svc(self):
        # has not been needed yet
        raise NotImplementedError()

    def handle_undefined_instruction(self):
        # has not been needed yet
        raise NotImplementedError()

    def handle_data_abort(self):
        # x14 => AArch32 lr
        lr = self._target_bridge.read_register("lr")
        abort_address = lr - 8
        self._logger.error(f"data abort exception in {hex(abort_address)}")

        dfsr = self._target_bridge.read_register("dfsr")
        fault_status = (dfsr & 0b10000000000) >> 6 | (dfsr & 0b1111)

        known_statuses = {
            0b00001: "alignment fault",
            0b00010: "debug exception",
            0b00011: "access flag fault, level 1",
            0b00100: "fault on instruction cache maintenance",
            0b00101: "translation fault, level 1",
            0b00110: "access flag fault, level 2",
            0b00111: "translation fault, level 2",
            0b01000: "synchronous external abort, not on translation table walk",
            0b01001: "domain fault, level 1",
            0b01100: "synchronous external abort, on translation table walk, level 1",
            0b01101: "permission fault, level 1",
            0b01110: "synchronous external abort, on translation table walk, level 2",
            0b01111: "permission fault, level 2",
            0b10000: "TLB conflict abort",
            0b10100: "implementation defined fault (lockdown fault)",
            0b10101: "implementation defined fault (unsupported exclusive access fault)",
            0b10110: "SError interrupt",
            0b11000: "SError interrupt, from a parity or ECC error on memory access (when FEAT_RAS is not implemented)",
            0b11001: "synchronous parity or ECC error on memory access, not on translation table walk (when FEAT_RAS is not implemented)",
            0b11100: "synchronous parity or ECC error on translation table walk, level 1 (when FEAT_RAS is not implemented)",
            0b11110: "synchronous parity or ECC error on translation table walk level 2 (when FEAT_RAS is not implemented)",
        }

        self._logger.error(f"DFSR fault status {bin(fault_status)}: {known_statuses[fault_status]}")
