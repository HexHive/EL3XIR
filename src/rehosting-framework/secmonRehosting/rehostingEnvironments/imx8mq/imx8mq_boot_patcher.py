from ... import get_logger
from ...helperScripts import BreakpointHandlerBase
from ..rehosting_context import RehostingContext


class Imx8mqBootPatcher(BreakpointHandlerBase):
    def __init__(self, rehosting_context: RehostingContext, enable_optional_patches: bool = False):
        super().__init__()

        self._context = rehosting_context

        # must-have patches
        self._breakpoints = {

            0x0091035c: "skip gic driver init",
            0x00910360: "skip plat gic init",

            # this is the NW entry address -> break here to make snapshot
            0x40200000: "SecMon is finished booting (first address in NW) -> taking snapshot..."
        }

        if enable_optional_patches:
            self._breakpoints.update(
                {

                }
            )

        self._logger = get_logger("imx8mq_boot_patcher")

        for bp_address in self._breakpoints.keys():
            self._register_handler_for_breakpoint(bp_address, self._handle_bp)

    def _handle_bp(self):
        bp_address = self._context.target_bridge.read_register("pc")

        if bp_address == 0x40200000:
            # here we use the qemu intern functionality to make a snapshot with name "booted"
            # it will later be loaded for fuzzing
            print(self._context.target.protocols.monitor.execute_command("human-monitor-command",
                                                                     {"command-line": "savevm booted"}))
            print(self._context.target.protocols.monitor.execute_command("human-monitor-command",
                                                                     {"command-line": "info snapshots"}))
            # after taking the snapshot we can just exit
            quit(0)

        if bp_address == 0x0091035c:
            self._context.target.write_register("pc", 0x00910360)
        if bp_address == 0x00910360:
            self._context.target.write_register("pc", 0x00910364)

        # print out some logging information
        self._logger.info(f"pc={hex(bp_address)}: {self._breakpoints[bp_address]}")
