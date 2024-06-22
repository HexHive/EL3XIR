import os

from avatar2 import AARCH64, Target

from .samsungS7_boot_patcher import SamsungS7BootPatcher
from .samsungS7_call_into_secmon_strategy import SamsungS7CallIntoSecMonStrategyBase
from ..avatar_factory_memory_mapping import AvatarFactoryMemoryMapping
from ..rehosting_context import RehostingContext
from ..secmon_runner import SecMonRunner
from ...helperScripts import ConvenientAvatar, BreakpointHandlingRunner
from ...helperScripts.colored_register_printer import ColoredRegistersPrinter
from ...helperScripts.keystone import aarch64_asm
from ...helperScripts.target_bridge import DefaultTargetBridge


class SecMonS7AvatarFactory:

    def __init__(self):
        # virtual hardware configuration
        self._arch = AARCH64
        self._avatar_cpu = "cortex-a53"

        # here our minimal bootloader emulating BL1/2 will take place
        self._entry_address = 0x2000

        # start at bl31_entrypoint
        self._secmon_addr = 0x02024010

        # tbase is aarch32 and is loaded by a secondary loader in NW
        # through interaction with the SecMon
        self._tzos_entry_addr = None

        # this is the entrypoint of the bl33 uboot booting sequence "first eret of SM boot into NW"
        # Samsung uses an uboot here which is in charge of loading a secondary image loader
        self._normal_entry_addr = 0x2048000

        self._sboot = AvatarFactoryMemoryMapping(0x2022000, 0x1B3000)

    def _write_normal_world_stub(self, target_bridge):

        normal_stub_code = f"""  
            smc #0
            smc #0
        """

        nw_stub_bytes = aarch64_asm(normal_stub_code)

        target_bridge.write_memory(self._normal_entry_addr, len(nw_stub_bytes), nw_stub_bytes, raw=True)

        return

    def _add_minimal_bootloader(self, avatar: ConvenientAvatar):
        bootloader_code = f"""
            mov x14, #{hex(self._secmon_addr)[:5]}
            lsl x14, x14, #16
            movk x14, #0x{hex(self._secmon_addr)[5:]}
            mov x11, #0x3cd
            msr spsr_el3, x11
            mrs x15, midr_el1
            ret x14
        """

        boot_bin_path = os.path.join(avatar.output_directory, "boot.bin")

        with open(boot_bin_path, "wb") as f:
            f.write(aarch64_asm(bootloader_code))

        return avatar.add_memory_range(self._entry_address, 0x00001000, name="bootloader_stub", file=boot_bin_path)

    def _create_target_bridge(self, target: Target):
        return DefaultTargetBridge(target)

    def get_rehosting_context(self, sboot_s7_path: str, avatar_output_dir: str = None):
        # check preconditions
        assert self._arch is not None

        avatar = ConvenientAvatar(
            arch=self._arch, output_directory=avatar_output_dir, log_to_stdout=False, cpu_model=self._avatar_cpu
        )

        # set the sboot path
        self._sboot_path = sboot_s7_path

        # create snapshot image
        os.system(f"qemu-img create -f qcow2 {avatar_output_dir}/snapshot.qcow2 200M")

        qemu_target = avatar.add_qemu_target(
            self._entry_address,
            enable_semihosting=True,
            additional_args=[
                "-d",
                "exec,cpu,int,in_asm",
                #"cpu_reset,guest_errors,int,cpu,in_asm,mmu",
                "-blockdev",
                f"node-name=node-A,driver=qcow2,file.driver=file,file.node-name=file,file.filename={avatar_output_dir}/snapshot.qcow2",
            ],
        )

        # this will add a minimal bootloader emulating BL1/2
        self._add_minimal_bootloader(avatar)

        avatar.add_memory_range(0x02020000, 0x2000, name="before_sboot")
        # here we map the sboot file 0x02022000 -  0x021d5000)
        avatar.add_memory_range(self._sboot.address, self._sboot.size, name="sboot", file=sboot_s7_path)
        avatar.add_in_memory_buffer_peripheral(0x02292000, 0x1000, name="after_sboot_test")
        # add MMIO regions or reflected peripheral modeling
        avatar.add_in_memory_buffer_peripheral(0x02293000, 0x7eeb7000, name="after_sboot0")
        avatar.add_in_memory_buffer_peripheral(0x8114a000, 0x3f75b800, name="after_sboot1")
        avatar.add_in_memory_buffer_peripheral(0xc08a5800, 0x1fbadc00, name="after_sboot2")
        avatar.add_in_memory_buffer_peripheral(0xe0453400, 0xfdd6e00, name="after_sboot3")
        avatar.add_in_memory_buffer_peripheral(0xf022a200, 0x7eeb700, name="after_sboot4")
        avatar.add_in_memory_buffer_peripheral(0xf8115900, 0x3f75b80, name="after_sboot5")
        avatar.add_in_memory_buffer_peripheral(0xfc08b480, 0x1fbadc0, name="after_sboot6")
        avatar.add_in_memory_buffer_peripheral(0xfe046240, 0xfdd6e0, name="after_sboot7")
        avatar.add_in_memory_buffer_peripheral(0xff023920, 0x7eeb70, name="after_sboot8")
        avatar.add_in_memory_buffer_peripheral(0xff812490, 0x6f4b70, name="after_sboot9")
        avatar.add_memory_range(0xFFF07000, 0x3000, name="after_sboot10")
        avatar.add_in_memory_buffer_peripheral(0xfff0a000, 0xf6000, name="after_sboot11")

        target_bridge = self._create_target_bridge(qemu_target)

        avatar.init_targets()

        # this will overwrite uboot instructions which are normally loaded at nw entry point
        # with SMC instructions which makes fuzzing later easier
        self._write_normal_world_stub(target_bridge)

        colored_register_printer = ColoredRegistersPrinter(target_bridge)

        rehosting_context = RehostingContext(
            avatar,
            qemu_target,
            target_bridge,
            colored_register_printer=colored_register_printer,
        )

        return rehosting_context

    def _make_call_into_secmon_strategy(self, rehosting_context: RehostingContext):
        return SamsungS7CallIntoSecMonStrategyBase(rehosting_context)

    def get_runner(self, rehosting_context: RehostingContext):
        runner = BreakpointHandlingRunner(rehosting_context.target)

        boot_patcher = SamsungS7BootPatcher(rehosting_context, self._sboot_path)
        runner.register_handler(boot_patcher)

        secmon_execution_strategy = self._make_call_into_secmon_strategy(rehosting_context)

        secmon_runner = SecMonRunner(runner, secmon_execution_strategy)
        return secmon_runner
