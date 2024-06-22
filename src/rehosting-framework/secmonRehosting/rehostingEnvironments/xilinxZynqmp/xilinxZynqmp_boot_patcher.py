from ... import get_logger
from ...helperScripts import BreakpointHandlerBase
from ..rehosting_context import RehostingContext


class XilinxZynqmpBootPatcher(BreakpointHandlerBase):
    def __init__(self, rehosting_context: RehostingContext, enable_optional_patches: bool = False):
        super().__init__()

        self._context = rehosting_context

        # must-have patches
        self._breakpoints = {
            0xfffea4dc: "set 3th bit in x2 indicating success in putc",
            0xfffea4cc: "set 3th bit in x2 indicating success in putc",

            0xfffeed34: "pm_get_api_version read from hardware -> indicate success",

            0xfffea89c: "overwrite spsr_el3 to disable jump to EL2",

            # this is the NW entry address -> break here to make snapshot
            0x08000000: "SecMon is finished booting (first address in NW) -> taking snapshot...",

        }

        if enable_optional_patches:
            self._breakpoints.update(
                {

                }
            )

        self._logger = get_logger("xilinxzynqmp_boot_patcher")

        for bp_address in self._breakpoints.keys():
            self._register_handler_for_breakpoint(bp_address, self._handle_bp)

    def _handle_bp(self):
        bp_address = self._context.target_bridge.read_register("pc")

        if bp_address == 0x08000000:
            # here we use the qemu intern functionality to make a snapshot with name "booted"
            # it will later be loaded for fuzzing
            print(self._context.target.protocols.monitor.execute_command("human-monitor-command",
                                                                     {"command-line": "savevm booted"}))
            print(self._context.target.protocols.monitor.execute_command("human-monitor-command",
                                                                     {"command-line": "info snapshots"}))
            # after taking the snapshot we can just exit
            quit(0)

        if bp_address == 0xfffea4dc:
            self._context.target_bridge.write_register("x2", 0x8)
        if bp_address == 0xfffea4cc:
            self._context.target_bridge.write_register("x2", 0x8)

        if bp_address == 0xfffea89c:
            self._context.target_bridge.write_register("x16", 0x3c4)

        if bp_address == 0xfffea4c0:
            char_print = self._context.target_bridge.read_register("x0")
            print(chr(char_print))

        if bp_address == 0xfffeed34:
            self._context.target_bridge.write_register("x3", 0x10001)

        # print out some logging information
        self._logger.info(f"pc={hex(bp_address)}: {self._breakpoints[bp_address]}")
