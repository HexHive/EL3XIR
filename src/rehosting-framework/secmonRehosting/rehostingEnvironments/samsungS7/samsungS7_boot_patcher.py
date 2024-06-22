from ... import get_logger
from ...helperScripts import BreakpointHandlerBase
from ..rehosting_context import RehostingContext


class SamsungS7BootPatcher(BreakpointHandlerBase):
    def __init__(self, rehosting_context: RehostingContext, sboot_path, enable_optional_patches: bool = False):
        super().__init__()

        self._context = rehosting_context

        self.sboot_path = sboot_path

        # must-have patches
        self._breakpoints = {
            0x0202f74c: "secmon bl31 set x0 to 0x4 to prevent wfi",
            0x0202eed8: "secmon bl31 set x0 to 0x1 to prevent fail - mpdir_el1",
            0x0202f780: "secmon bl31 set x1 to 0xdab to prevent mmu enable - no xlat tables set",
            0x0203091c: "secmon bl31 set x4 to 0x0 seems like hardware wait",
            0x0202eac8: "secmon bl31 set x0 to 0x1 from vbar check to not enable mmu",
            0x02030840: "secmon bl31 set x1 to 0xf seems like hardware wait",
            0x020258b0: "secmon bl31 skip blr x0 will lead to undef instruction",
            0x02024be8: "secmon bl31 skip blr x4 will lead to undef instruction",

            0x02049c2c: "uboot bl33 set x0 to 0x20000000 (29th bit) seems like hardware wait",
            0x02049c64: "uboot bl33 set x0 to 0x20000000 (29th bit) seems like hardware wait",
            0x02049c70: "uboot bl33 set x0 to 0x20000000 (29th bit) seems like hardware wait",
            0x02049cd4: "uboot bl33 set x0 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204a6d8: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204a82c: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204c7e8: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204c7f8: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204c808: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204c818: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204a9a0: "uboot bl33 set x0 to 0x0 (31th and 30th bit not set) seems like hardware wait",
            0x0204adf8: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204ae9c: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204b3c4: "uboot bl33 set x0 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204b794: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204bed8: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204e130: "uboot bl33 set x0 to 0x2 (1th bit) seems like hardware wait",
            0x0204e138: "uboot bl33 set x0 to 0x2 (1th bit) seems like hardware wait",
            0x0204e140: "uboot bl33 set x0 to 0x2 (1th bit) seems like hardware wait",
            0x0204e148: "uboot bl33 set x0 to 0x2 (1th bit) seems like hardware wait",
            0x0204fd04: "uboot bl33 set x0 to x1 long loop where counter seems to be sub by zero...?",
            0x0204d848: "uboot bl33 set x0 to 0xf seems like hardware wait",
            0x0204d984: "uboot bl33 set x0 to 0x1 (non zero) seems like hardware wait",
            0x0204d988: "uboot bl33 set x21 to 0x1 (non zero) seems like hardware wait",
            0x0204dab8: "uboot bl33 set x23 to 0x1 (non zero) seems like hardware wait",
            0x0204ece0: "uboot bl33 set x0 to 0x100000000 (32th bit) seems like hardware wait",
            0x0204aa84: "uboot bl33 set x1 to 0x20000000 (29th bit) seems like hardware wait",
            0x0204d65c: "uboot bl33 set x0 to 0x1 (non zero) seems like hardware wait",
            0x0204e4d8: "uboot bl33 set x0 to 0x8 (3th bit) seems like hardware wait",
            0x0204e4e4: "uboot bl33 set x0 to 0x8 (3th bit) seems like hardware wait",
            0x0204e4f0: "uboot bl33 set x0 to 0x8 (3th bit) seems like hardware wait",
            0x0204e4fc: "uboot bl33 set x0 to 0x8 (3th bit) seems like hardware wait",
            0x0204f8d8: "uboot bl33 set x0 to 0x1 (non zero) seems like hardware wait",
            0x0204a9c4: "uboot bl33 set x1 to 0x0 (31th and 30th bit not set) seems like hardware wait",
            0x0204fd54: "uboot bl33 set x2 to 0xcb000000 indicating UFS bootdev",
            0x0204fd74: "uboot bl33 set x0 to 0x1 indicating UFS bootdev 0x20 in x0",

            # this is the NW entry address -> break here to make snapshot
            0x02048000: "SecMon is finished booting (first address in NW) -> taking snapshot..."

        }

        if enable_optional_patches:
            self._breakpoints.update(
                {

                }
            )

        self._logger = get_logger("samsungs7_boot_patcher")

        for bp_address in self._breakpoints.keys():
            self._register_handler_for_breakpoint(bp_address, self._handle_bp)

    def _handle_bp(self):
        bp_address = self._context.target_bridge.read_register("pc")

        if bp_address == 0x02048000:
            # here we use the qemu intern functionality to make a snapshot with name "booted"
            # it will later be loaded for fuzzing
            print(self._context.target.protocols.monitor.execute_command("human-monitor-command",
                                                                     {"command-line": "savevm booted"}))
            print(self._context.target.protocols.monitor.execute_command("human-monitor-command",
                                                                     {"command-line": "info snapshots"}))
            # after taking the snapshot we can just exit
            quit(0)

        if bp_address == 0x0202f74c:
            self._context.target_bridge.write_register("x0", 0x4)
        if bp_address == 0x0202eed8:
            self._context.target_bridge.write_register("x0", 0x1)
        if bp_address == 0x0202f780:
            self._context.target_bridge.write_register("x1", 0xdab)
        if bp_address == 0x0203091c:
            self._context.target_bridge.write_register("x4", 0x0)
        if bp_address == 0x0202eac8:
            self._context.target_bridge.write_register("x0", 0x1)
        if bp_address == 0x02030840:
            self._context.target_bridge.write_register("x1", 0xf)

        if bp_address == 0x020258b0:
            self._context.target_bridge.write_register("pc", 0x020258b4)
        if bp_address == 0x02024be8:
            self._context.target_bridge.write_register("pc", 0x02024bec)

        if bp_address == 0x02049c2c:
            self._context.target_bridge.write_register("x0", 0x20000000)
        if bp_address == 0x02049c64:
            self._context.target_bridge.write_register("x0", 0x20000000)
        if bp_address == 0x02049c70:
            self._context.target_bridge.write_register("x0", 0x20000000)
        if bp_address == 0x02049cd4:
            self._context.target_bridge.write_register("x0", 0x20000000)
        if bp_address == 0x0204a6d8:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204a82c:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204c7e8:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204c7f8:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204c808:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204c818:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204a9a0:
            self._context.target_bridge.write_register("x0", 0x0)
        if bp_address == 0x0204adf8:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204ae9c:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204b3c4:
            self._context.target_bridge.write_register("x0", 0x20000000)
        if bp_address == 0x0204b794:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204bed8:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204e130:
            self._context.target_bridge.write_register("x0", 0x2)
        if bp_address == 0x0204e138:
            self._context.target_bridge.write_register("x0", 0x2)
        if bp_address == 0x0204e140:
            self._context.target_bridge.write_register("x0", 0x2)
        if bp_address == 0x0204e148:
            self._context.target_bridge.write_register("x0", 0x2)
        if bp_address == 0x0204fd04:
            self._context.target_bridge.write_register("x0", self._context.target_bridge.read_register("x1"))
        if bp_address == 0x0204d848:
            self._context.target_bridge.write_register("x0", 0xf)
        if bp_address == 0x0204d984:
            self._context.target_bridge.write_register("x0", 0x1)
        if bp_address == 0x0204d988:
            self._context.target_bridge.write_register("x21", 0x1)
        if bp_address == 0x0204dab8:
            self._context.target_bridge.write_register("x23", 0x1)
        if bp_address == 0x0204ece0:
            self._context.target_bridge.write_register("x0", 0x100000000)
        if bp_address == 0x0204aa84:
            self._context.target_bridge.write_register("x1", 0x20000000)
        if bp_address == 0x0204d65c:
            self._context.target_bridge.write_register("x0", 0x1)
        if bp_address == 0x0204e4d8:
            self._context.target_bridge.write_register("x0", 0x8)
        if bp_address == 0x0204e4e4:
            self._context.target_bridge.write_register("x0", 0x8)
        if bp_address == 0x0204e4f0:
            self._context.target_bridge.write_register("x0", 0x8)
        if bp_address == 0x0204e4fc:
            self._context.target_bridge.write_register("x0", 0x8)
        if bp_address == 0x0204f8d8:
            self._context.target_bridge.write_register("x0", 0x1)
        if bp_address == 0x0204a9c4:
            self._context.target_bridge.write_register("x1", 0x0)
        if bp_address == 0x0204fd54:
            self._context.target_bridge.write_register("x0", 0xcb000000)
        if bp_address == 0x0204fedc:
            self._context.target_bridge.write_register("x0", 0x0)
        if bp_address == 0x020480ec:
            self._context.target_bridge.write_register("pc", 0x020480f0)
        if bp_address == 0x0204fedc:
            self._context.target_bridge.write_register("x0", 0x0)
        if bp_address == 0x0204fd74:
            self._context.target_bridge.write_register("x0", 0x1)
        if bp_address == 0x02024fa0:
            self._context.target_bridge.write_register("x0", 0x0)
        if bp_address == 0x02028f9c:
            self._context.target_bridge.write_register("pc", 0x02028fa0)

        # print out some logging information
        self._logger.info(f"pc={hex(bp_address)}: {self._breakpoints[bp_address]}")
