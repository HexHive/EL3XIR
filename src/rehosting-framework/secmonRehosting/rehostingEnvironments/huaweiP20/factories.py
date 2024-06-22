import os

from avatar2 import AARCH64, Target, QemuTarget

from .huaweiP20_boot_patcher import HuaweiP20BootPatcher
from .huaweiP20_call_into_secmon_strategy import HuaweiP20CallIntoSecMonStrategyBase
from ..avatar_factory_memory_mapping import AvatarFactoryMemoryMapping
from ..rehosting_context import RehostingContext
from ..secmon_runner import SecMonRunner
from ..structs import Bl31Params, EntryPointInfo, ImageInfo, BlParam
from ...helperScripts import ConvenientAvatar, BreakpointHandlingRunner
from ...helperScripts.colored_register_printer import ColoredRegistersPrinter
from ...helperScripts.keystone import aarch64_asm, aarch32_asm
from ...helperScripts.target_bridge import DefaultTargetBridge


class SecMonP20AvatarFactory:

    def __init__(self):
        # virtual hardware configuration
        self._arch = AARCH64
        self._avatar_cpu = "cortex-a53"

        # here our minimal bootloader emulating BL1/2 will take place
        self._entry_address = 0x1000

        # start at bl31_entrypoint
        self._secmon_addr = 0x35e00000

        # addr where bl params will be added
        self._bl_params_addr = 0x35e80000

        # this is the entrypoint of the TZOS booting sequence "first eret of SM boot"
        # secmon and run it standalone
        self._tzos_entry_addr = 0x36200000

        # this is the entrypoint of the rich OS booting "last eret of SM boot"
        self._normal_entry_addr = 0x480000

        self._secmon_binary = AvatarFactoryMemoryMapping(0x35e00000, 0x41000)

    def _add_normal_world_stub(self, avatar: ConvenientAvatar):

        normal_stub_code = f"""
            smc #0
            smc #0
        """

        boot_bin_path = os.path.join(avatar.output_directory, "normal_stub.bin")

        with open(boot_bin_path, "wb") as f:
            f.write(aarch64_asm(normal_stub_code))

        return avatar.add_memory_range(self._normal_entry_addr, 0x00001000, name="normal_world_stub", file=boot_bin_path)

    def _add_secure_world_stub(self, avatar: ConvenientAvatar):

        secure_stub_code = f"""
            mov r0,#0xb2000000
            mov r1,#0x36000000
            mov r2,#0x200000
            mov r3,#0x4000
            orr r1,r1,r2
            orr r1,r1,r3
            smc #0
        """

        boot_bin_path = os.path.join(avatar.output_directory, "secure_stub.bin")

        with open(boot_bin_path, "wb") as f:
            f.write(aarch32_asm(secure_stub_code))

        return avatar.add_memory_range(self._tzos_entry_addr, 0x00001000, name="secure_world_stub", file=boot_bin_path)


    def _write_bl_params_to_memory(self, target: DefaultTargetBridge, base_addr: int):
        bl32_base = 0x36200000
        bl32_size = 0x01E00000
        bl33_base = 0x00480000
        bl33_size = 0x00008000

        offset = 0
        bl_list = dict()
        bl_list["bl32_ep"] = BlParam(base_addr + Bl31Params.calcsize() + offset, EntryPointInfo(bl32_base, 0, [], 0))
        bl_list["bl33_ep"] = BlParam(
            bl_list["bl32_ep"].addr + EntryPointInfo.calcsize() + offset, EntryPointInfo(bl33_base, 0x3C4, [], 1)
        )
        bl_list["bl32_image"] = BlParam(
            bl_list["bl33_ep"].addr + ImageInfo.calcsize() + offset, ImageInfo(bl32_base, bl32_size, 0)
        )
        bl_list["bl33_image"] = BlParam(
            bl_list["bl32_image"].addr + ImageInfo.calcsize() + offset, ImageInfo(bl33_base, bl33_size, 0)
        )
        bl_list["bl31_params"] = BlParam(
            base_addr,
            Bl31Params(
                1234,
                bl_list["bl32_ep"].addr,
                bl_list["bl32_image"].addr,
                bl_list["bl33_ep"].addr,
                bl_list["bl33_image"].addr,
            ),
        )
        bl_params = (
                bl_list["bl31_params"].structure.to_bytes()
                + bl_list["bl32_ep"].structure.to_bytes()
                + bl_list["bl33_ep"].structure.to_bytes()
                + bl_list["bl32_image"].structure.to_bytes()
                + bl_list["bl33_image"].structure.to_bytes()
        )

        target.write_memory(base_addr, len(bl_params), bl_params, raw=True)

    def _add_minimal_bootloader(self, avatar: ConvenientAvatar):
        bootloader_code = f"""
            mov x0, #{hex(self._bl_params_addr)}
            mov x1, #0x6978
            movk x1, #0x4B5A, lsl #16
            movk x1, #0x2D3C, lsl #32
            movk x1, #0x0F1E, lsl #48
            mov x14, #{hex(self._secmon_addr)[:6]}
            lsl x14, x14, #16
            movk x14, #0x{hex(self._secmon_addr)[6:]}
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

    def get_rehosting_context(self, secmon_binary_path: str, avatar_output_dir: str = None):
        # check preconditions
        assert self._arch is not None

        avatar = ConvenientAvatar(
            arch=self._arch, output_directory=avatar_output_dir, log_to_stdout=False, cpu_model=self._avatar_cpu
        )

        # create snapshot image
        os.system(f"qemu-img create -f qcow2 {avatar_output_dir}/snapshot.qcow2 200M")

        qemu_target = avatar.add_qemu_target(
            self._entry_address,
            enable_semihosting=True,
            additional_args=[
                "-d",
                "exec",
                #"cpu_reset,guest_errors,int,cpu,in_asm,mmu",
                "-blockdev",
                f"node-name=node-A,driver=qcow2,file.driver=file,file.node-name=file,file.filename={avatar_output_dir}/snapshot.qcow2",
            ],
        )

        self._add_normal_world_stub(avatar)

        # here we map the secmon binary file
        avatar.add_memory_range(self._secmon_binary.address, self._secmon_binary.size, name="secmon_binary", file=secmon_binary_path)

        avatar.add_memory_range(0x0, 0x1000, name="before_minimal_bootloader")
        # minimal bootloader emulating BL1/2 at 0x1000 - 0x2000
        self._add_minimal_bootloader(avatar)
        avatar.add_memory_range(0x2000, 0x35e00000-0x2000, name="before_secmon_binary")
        avatar.add_memory_range(0x35E41000, 0x3BF000, name="after_secmon_binary")
        # secure world stub at 0x36200000 - 0x36201000
        self._add_secure_world_stub(avatar)
        avatar.add_memory_range(0x36201000, 0xC7D01000, name="after_secure_stub")
        avatar.add_pl011(0xFDF02000, 0x00001000, "uart", 0)
        # add MMIO regions or reflected peripheral modeling
        avatar.add_in_memory_buffer_peripheral(0xFDF03000, 0x1000000, name="after_uart")
        avatar.add_in_memory_buffer_peripheral(0xFEF03000, 0x1000000, name="after_uart1")
        avatar.add_in_memory_buffer_peripheral(0xFFF03000, 0x4000, name="after_uart0")
        avatar.add_memory_range(0xFFF07000, 0x3000, name="after_uart4")
        avatar.add_in_memory_buffer_peripheral(0xfff0a000, 0x1000, name="after_uart2")
        avatar.add_in_memory_buffer_peripheral(0xfff0b000, 0xf5000, name="after_uart3")

        avatar.init_targets()

        target_bridge = self._create_target_bridge(qemu_target)

        # add bl params after mappings and target is initialized
        self._write_bl_params_to_memory(target_bridge, self._bl_params_addr)

        colored_register_printer = ColoredRegistersPrinter(target_bridge)

        rehosting_context = RehostingContext(
            avatar,
            qemu_target,
            target_bridge,
            colored_register_printer=colored_register_printer,
        )

        return rehosting_context

    def _make_call_into_secmon_strategy(self, rehosting_context: RehostingContext):
        return HuaweiP20CallIntoSecMonStrategyBase(rehosting_context)

    def get_runner(self, rehosting_context: RehostingContext):
        runner = BreakpointHandlingRunner(rehosting_context.target)

        boot_patcher = HuaweiP20BootPatcher(rehosting_context)
        runner.register_handler(boot_patcher)

        secmon_execution_strategy = self._make_call_into_secmon_strategy(rehosting_context)

        secmon_runner = SecMonRunner(runner, secmon_execution_strategy)
        return secmon_runner
