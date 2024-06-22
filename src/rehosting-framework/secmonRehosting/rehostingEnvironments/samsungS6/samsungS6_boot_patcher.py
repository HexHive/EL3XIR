from ... import get_logger
from ...helperScripts import BreakpointHandlerBase
from ..rehosting_context import RehostingContext


class SamsungS6BootPatcher(BreakpointHandlerBase):
    def __init__(self, rehosting_context: RehostingContext, sboot_path, enable_optional_patches: bool = False):
        super().__init__()

        self._context = rehosting_context

        self._logstring = ""

        self.sboot_path = sboot_path

        # must-have patches
        self._breakpoints = {

            0x0210e0f4: "seems like hardware wait at 0x105c2b04",
            0x0210c414: "seems like hardware wait at 0x02157048",
            0x0210c474: "seems like hardware wait at 0x02157048",
            0x0210c690: "inside platoform_init",
            0x0210c6d0: "inside platform_init to prevent enable mmu",
            0x0210bbc0: "make vbar_el3 check not enable mmu",
            0x0210e040: "seems like hardware wait at 0x105c2404",

            # callbacks are not loaded -> skip
            0x02105338: "skip some blr to x0",
            0x02104a08: "skip some blr to x3",

            0x02104624: "set return of func inside bl31_platform_setup",

            # later secmon during/after bl33 uboot
            0x02104ab0: "skip during/after bl33 uboot some blr x1 in load_image UFS",
            0x02104ae8: "skip during/after bl33 uboot some blr x7 does 0xa blk loading",
            0x02104b0c: "skip during/after bl33 uboot some blr x7 does less than 0xa blk loading",
            0x02104aec: "expects x0 to return 0x1 after blr to x7",
            0x02104b10: "expects x0 to return 0x1 after blr to x7",

            # hardware read values in bl33 uboot
            0x02134ca0: "uboot hw expects 0x20000 in x0",
            0x02134cd4: "uboot hw expects 0x111110 in x0",
            0x02134d04: "uboot hw expects 0x10000 in x0",
            0x02134474: "uboot hw expects 0x1 in x0",
            0x021344a8: "uboot hw expects 0x0 in x1",
            0x02134568: "uboot hw expects 0x0 in x1",
            0x02134704: "uboot hw expects 0x0 in x1",
            0x02134820: "uboot hw expects 0x0 in x1",
            0x021349f8: "uboot hw expects 0x0 in x1",
            0x02134b18: "uboot hw expects 0x0 in x1",
            0x021352c4: "uboot hw expects 0x21111 in x0",
            0x021352f8: "uboot hw expects 0x111111 in x0",
            0x0213532c: "uboot hw expects 0x11111 in x0",
            0x0213538c: "uboot hw expects 0x11110 in x0",
            # other uboot patches
            0x02137094: "uboot write higher 0x31f in x0",
            0x021354c8: "uboot write value where 0x20-th bit is not zero in x1",
            0x02137908: "uboot write non-zero in x0",
            0x02135af0: "uboot write value where 0xe-th bit is not zero in x1",
            0x02135b70: "uboot write value where 0xe-th bit is not zero in x3",
            0x02136d78: "uboot write value where 0xe-th bit is not zero in x4",
            0x02136cb4: "uboot write value where 0xe-th bit is not zero in x3",

            # secondary image bl33 stuff
            # in sboot image at address 0x02134000 but loaded at 0x43e00000
            0x43e15444: "set x1 to 0x2 (1th bit set) seems like hardware wait",
            0x43e05e08: "write x0 out as char",

            0x43e2fc20: "skip MUIC API and prevent error",
            0x43e03bdc: "skip function call",
            0x43e03be8: "skip function call",
            0x43e03c14: "skip function call",
            0x43e03c24: "skip function call muic_is_max",

            # this is the NW entry address -> break here to make snapshot
            0x02134000: "SecMon is finished booting (first address in NW) -> taking snapshot..."

        }

        if enable_optional_patches:
            self._breakpoints.update(
                {

                }
            )

        self._logger = get_logger("samsungs6_boot_patcher")

        for bp_address in self._breakpoints.keys():
            self._register_handler_for_breakpoint(bp_address, self._handle_bp)

    def _handle_bp(self):
        bp_address = self._context.target_bridge.read_register("pc")

        if bp_address == 0x43e00000 or bp_address == 0x02134000:
            # here we use the qemu intern functionality to make a snapshot with name "booted"
            # it will later be loaded for fuzzing
            print(self._context.target.protocols.monitor.execute_command("human-monitor-command",
                                                                     {"command-line": "savevm booted"}))
            print(self._context.target.protocols.monitor.execute_command("human-monitor-command",
                                                                     {"command-line": "info snapshots"}))
            # after taking the snapshot we can just exit
            quit(0)

        if bp_address == 0x02104040:
            self._context.target_bridge.write_register("x21", 0x11000000)
        if bp_address == 0x0210ded4:
            self._context.target_bridge.write_register("x21", 0x1)
        if bp_address == 0x0210df24:
            self._context.target_bridge.write_register("pc", 0x0210df28)

        # platform_is_primary_cpu needs to return 0x1 here
        if bp_address == 0x02104054:
            self._context.target_bridge.write_register("x0", 0x1)

        # in secmon during/after tbase boot
        if bp_address == 0x02104aec:
            self._context.target_bridge.write_register("x0", 0x1)
        if bp_address == 0x02104b10:
            self._context.target_bridge.write_register("x0", 0x1)


        if bp_address == 0x02104624:
            self._context.target_bridge.write_register("x0", 0x0)


        if bp_address == 0x0210e0f4:
            self._context.target_bridge.write_register("x2", 0x1)
        if bp_address == 0x0210c414:
            self._context.target_bridge.write_register("x4", 0x0)
        if bp_address == 0x0210c474:
            self._context.target_bridge.write_register("x4", 0x0)
        if bp_address == 0x0210c690:
            self._context.target_bridge.write_register("x0", 0x4)
        # this can prevent enable mmu
        if bp_address == 0x0210c6d0:
            self._context.target_bridge.write_register("x1", 0xbad)
        if bp_address == 0x0210bbc0:
            self._context.target_bridge.write_register("x0", 0x1)

        if bp_address == 0x0210e040:
            self._context.target_bridge.write_register("x1", 0xf)

        # skip some callbacks
        if bp_address == 0x02105338:
            self._context.target_bridge.write_register("pc", 0x0210533c)
        if bp_address == 0x02104a08:
            self._context.target_bridge.write_register("pc", 0x02104a0c)
        if bp_address == 0x021052fc:
            self._context.target_bridge.write_register("pc", 0x02105300)
        if bp_address == 0x02104ab0:
            self._context.target_bridge.write_register("pc", 0x02104ab4)
        if bp_address == 0x02104ae8:
            # here a UFS function copying memory is expected
            dst = self._context.target_bridge.read_register("x3")
            blkstart = self._context.target_bridge.read_register("x4")
            offset = blkstart * 0x1000
            # it seems that always 0xa bulk of size 0x1000 per call -> 0xa000 bytes
            with open(self.sboot_path, "rb") as f:
                f.seek(offset)
                mem_content = f.read(0xa000)
                self._context.target_bridge.write_memory(dst, 0xa000, mem_content, raw=True)

            self._context.target_bridge.write_register("pc", 0x02104aec)
        if bp_address == 0x02104b0c:
            self._context.target_bridge.write_register("pc", 0x02104b10)

        # uboot
        # hardware waits
        if bp_address == 0x02134ca0:
            self._context.target_bridge.write_register("x0", 0x20000)
        if bp_address == 0x02134cd4:
            self._context.target_bridge.write_register("x0", 0x111110)
        if bp_address == 0x02134d04:
            self._context.target_bridge.write_register("x0", 0x10000)
        if bp_address == 0x02134474:
            self._context.target_bridge.write_register("x0", 0x1)
        if bp_address == 0x021344a8:
            self._context.target_bridge.write_register("x1", 0x0)
        if bp_address == 0x02134568:
            self._context.target_bridge.write_register("x1", 0x0)
        if bp_address == 0x02134704:
            self._context.target_bridge.write_register("x1", 0x0)
        if bp_address == 0x02134820:
            self._context.target_bridge.write_register("x1", 0x0)
        if bp_address == 0x021349f8:
            self._context.target_bridge.write_register("x1", 0x0)
        if bp_address == 0x02134b18:
            self._context.target_bridge.write_register("x1", 0x0)
        if bp_address == 0x021352c4:
            self._context.target_bridge.write_register("x0", 0x21111)
        if bp_address == 0x021352f8:
            self._context.target_bridge.write_register("x0", 0x111111)
        if bp_address == 0x0213532c:
            self._context.target_bridge.write_register("x0", 0x11111)
        if bp_address == 0x0213538c:
            self._context.target_bridge.write_register("x0", 0x11110)

        if bp_address == 0x02137094:
            self._context.target_bridge.write_register("x0", 0x320)
        if bp_address == 0x021354c8:
            self._context.target_bridge.write_register("x1", 0xffffffffffffffff)
        if bp_address == 0x02137908:
            self._context.target_bridge.write_register("x0", 0x1)
        if bp_address == 0x02135af0:
            self._context.target_bridge.write_register("x1", 0xffffffffffffffff)
        if bp_address == 0x02135b70:
            self._context.target_bridge.write_register("x3", 0xffffffffffffffff)
        if bp_address == 0x02136d78:
            self._context.target_bridge.write_register("x4", 0xffffffffffffffff)
        if bp_address == 0x02136cb4:
            self._context.target_bridge.write_register("x3", 0xffffffffffffffff)

        # secondary image
        if bp_address == 0x43e15444:
            self._context.target_bridge.write_register("x1", 0x2)
        if bp_address == 0x43e05e08:
            self._logstring += chr(self._context.target_bridge.read_register("x0"))
            print(self._logstring)
        if bp_address == 0x43e2fc20:
            self._context.target_bridge.write_register("pc", 0x43e2fc28)
        if bp_address == 0x43e03bdc:
            self._context.target_bridge.write_register("pc", 0x43e03be0)
        if bp_address == 0x43e03be8:
            self._context.target_bridge.write_register("pc", 0x43e03bec)
        if bp_address == 0x43e03c14:
            self._context.target_bridge.write_register("pc", 0x43e03c18)
        if bp_address == 0x43e03c24:
            self._context.target_bridge.write_register("pc", 0x43e03c28)

        # skip TBASE boot
        if bp_address == 0x43e03cd0:
            self._context.target_bridge.write_register("x0", 0x0)
            self._context.target_bridge.write_register("pc", 0x43e03cd4)

        if bp_address == 0x43e21cd8:
            self._context.target_bridge.write_register("x0", 0x0)

        if bp_address == 0x43e03dc8:
            self._context.target_bridge.write_register("pc", 0x43e03dcc)

        # print out some logging information
        self._logger.info(f"pc={hex(bp_address)}: {self._breakpoints[bp_address]}")
