from ... import get_logger
from ...helperScripts import BreakpointHandlerBase
from ..rehosting_context import RehostingContext


class NvidiaT186BootPatcher(BreakpointHandlerBase):
    def __init__(self, rehosting_context: RehostingContext, enable_optional_patches: bool = False):
        super().__init__()

        self._context = rehosting_context

        # must-have patches
        self._breakpoints = {
            0x30001d18: "set x2 which holds read midr_el1 to nvidia platform expected value",
            0x30005d44: "set x0 to return addr to bl params",
            0x30005d58: "set x0 to return addr to plat params",
            0x30005c60: "set x0 to indicate chip_id t186",
            0x30005090: "set x0 to indicate emulated platform",
            0x30004004: "set x1 to indicate gic success init",
            0x30009fcc: "set x3 to poll success hardware",
            0x30009fe0: "set x1 to poll success hardware",
            0x3000a01c: "set x2 to poll success hardware",
            0x3000a030: "set x0 to poll success hardware",

            # this is the NW entry address -> break here to make snapshot
            0x80000000: "SecMon is finished booting (first address in NW) -> taking snapshot...",

        }

        if enable_optional_patches:
            self._breakpoints.update(
                {

                }
            )

        self._logger = get_logger("nvidiat186_boot_patcher")

        for bp_address in self._breakpoints.keys():
            self._register_handler_for_breakpoint(bp_address, self._handle_bp)

    def _handle_bp(self):
        bp_address = self._context.target_bridge.read_register("pc")

        if bp_address == 0x80000000:
            # here we use the qemu intern functionality to make a snapshot with name "booted"
            # it will later be loaded for fuzzing
            print(self._context.target.protocols.monitor.execute_command("human-monitor-command",
                                                                     {"command-line": "savevm booted"}))
            print(self._context.target.protocols.monitor.execute_command("human-monitor-command",
                                                                     {"command-line": "info snapshots"}))
            # after taking the snapshot we can just exit
            quit(0)

        if bp_address == 0x30001d18:
            self._context.target_bridge.write_register("x2", 0x4100d070)

        if bp_address == 0x30005d44:
            self._context.target_bridge.write_register("x0", 0x2000)
        
        if bp_address == 0x30005d58:
            self._context.target_bridge.write_register("x0", 0x3000)
        
        if bp_address == 0x30005c60:
            self._context.target_bridge.write_register("x0", 0xff)
        
        if bp_address == 0x30005090:
            self._context.target_bridge.write_register("x0", 0xff)
        
        if bp_address == 0x30004004:
            self._context.target_bridge.write_register("x1", 0x0)

        if bp_address == 0x30009fcc:
            self._context.target_bridge.write_register("x3", 0x188081)

        if bp_address == 0x30009fe0:
            self._context.target_bridge.write_register("x1", 0x188081)

        if bp_address == 0x3000a01c:
            self._context.target_bridge.write_register("x2", 0x1dc10c1)

        if bp_address == 0x3000a030:
            self._context.target_bridge.write_register("x0", 0x1dc10c1)

        # print out some logging information
        self._logger.info(f"pc={hex(bp_address)}: {self._breakpoints[bp_address]}")
