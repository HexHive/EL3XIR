import os

from avatar2 import AARCH64, Target

from .xilinxZynqmp_boot_patcher import XilinxZynqmpBootPatcher
from .xilinxZynqmp_call_into_secmon_strategy import XilinxZynqmpCallIntoSecMonStrategyBase
from ..avatar_factory_memory_mapping import AvatarFactoryMemoryMapping
from ..rehosting_context import RehostingContext
from ..secmon_runner import SecMonRunner
from ..structs import Bl31Params, EntryPointInfo, ImageInfo, BlParam
from ...helperScripts import ConvenientAvatar, BreakpointHandlingRunner
from ...helperScripts.colored_register_printer import ColoredRegistersPrinter
from ...helperScripts.keystone import aarch64_asm
from ...helperScripts.target_bridge import DefaultTargetBridge


class SecMonZynqmpAvatarFactory:

    def __init__(self):
        # virtual hardware configuration
        self._arch = AARCH64
        self._avatar_cpu = "cortex-a53"

        # here our minimal bootloader emulating BL1/2 will take place
        self._entry_address = 0x00001000

        # start at bl31_entrypoint
        # BL31_BASE taken from platform_def.h in /plat/xilinx/zynqmp/include
        self._secmon_addr = 0xfffea000

        # addr where bl params will be added
        self._bl_params_addr = 0xffff7d30

        # this is the entrypoint of the TZOS booting sequence "first eret of SM boot"
        # this address can be defined in the bl_params (here an arbitrary address is choosen)
        self._tzos_entry_addr = 0x60000000

        # this is the entrypoint of the rich OS booting "last eret of SM boot"
        # this address can be defined in the bl_params (here an arbitrary address is choosen)
        self._normal_entry_addr = 0x08000000

        # map secure monitor binary here
        # BL31_BASE and BL31_LIMIT to calc size
        # make BL31 size smaller to fit at least the binary
        # space for MMIO regions after secmon memory
        self.secmon_binary = AvatarFactoryMemoryMapping(0xfffea000, 0xd000)

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
            mov x0,#0xBE000000
            mov x1,#0xABCD0000
            smc #0
        """

        boot_bin_path = os.path.join(avatar.output_directory, "secure_stub.bin")

        with open(boot_bin_path, "wb") as f:
            f.write(aarch64_asm(secure_stub_code))

        return avatar.add_memory_range(self._tzos_entry_addr, 0x00001000, name="secure_world_stub", file=boot_bin_path)


    def _write_bl_params_to_memory(self, target: DefaultTargetBridge, base_addr: int):
        bl32_base = 0x60000000
        bl32_size = 0x7fffffff
        bl33_base = 0x08000000
        bl33_size = 0x00008000

        # try to write spsr_el3 to indicate that we want to go to EL1
        target.write_memory(base_addr + 0x10, 0x8, 0x3c4)

    def _add_minimal_bootloader(self, avatar: ConvenientAvatar):
        bootloader_code = f"""
            mov x0, #0xAAAA
            lsl x0, x0, #16
            movk x0, #0xAAAA
            mov x1, #0xBBBB
            lsl x1, x1, #16
            movk x1, #0xBBBB
            mov x14, #{hex(self._secmon_addr)[:6]}
            lsl x14, x14, #16
            movk x14, #0x{hex(self._secmon_addr)[6:]}
            ret x14
        """
        print(bootloader_code)

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
                "exec,cpu,int,in_asm",
                #"cpu_reset,guest_errors,int,cpu,in_asm,mmu",
                "-blockdev",
                f"node-name=node-A,driver=qcow2,file.driver=file,file.node-name=file,file.filename={avatar_output_dir}/snapshot.qcow2",
            ],
        )

        # this will add a minimal bootloader emulating BL1/2 and NW and SW stubs
        self._add_minimal_bootloader(avatar)
        self._add_normal_world_stub(avatar)
        self._add_secure_world_stub(avatar)

        # here we map the secmon binary file
        avatar.add_memory_range(self.secmon_binary.address, self.secmon_binary.size, name="secmon_binary", file=secmon_binary_path)

        # map in rest of memory
        avatar.add_memory_range(0x0, 0x1000, name="before_bootloader")
        # bootloader from 0x1000 to 0x2000
        avatar.add_memory_range(0x2000, 0x7ffe000, name="before_normal_stub")
        # normal world entry stub from 0x08000000 until 0x08001000
        avatar.add_memory_range(0x08001000, 0x57fff000, name="after_normal_stub")
        # secure world stub from 0x60000000 until 0x60001000
        avatar.add_memory_range(0x60001000, 0x9efff000, name="after_secure_stub")
        avatar.add_pl011(0xff000000, 0x1000, "uart0", 0)
        avatar.add_in_memory_buffer_peripheral(0xff001000, 0xf000, name="between_uart")
        avatar.add_pl011(0xff010000, 0x1000, "uart1", 1)
        # add MMIO regions or reflected peripheral modeling
        avatar.add_in_memory_buffer_peripheral(0xff011000, 0x97e000, name="before_secmon_binary")
        avatar.add_memory_range(0xff98f000, 0x65b000, name="before_secmon_binary1")
        # secmon binary 0xfffea000 - 0xffff7000
        avatar.add_memory_range(0xffff7000, 0x9000, name="before_secmon_binary2")

        avatar.init_targets()

        target_bridge = self._create_target_bridge(qemu_target)

        colored_register_printer = ColoredRegistersPrinter(target_bridge)

        rehosting_context = RehostingContext(
            avatar,
            qemu_target,
            target_bridge,
            colored_register_printer=colored_register_printer,
        )

        return rehosting_context

    def _make_call_into_secmon_strategy(self, rehosting_context: RehostingContext):
        return XilinxZynqmpCallIntoSecMonStrategyBase(rehosting_context)

    def get_runner(self, rehosting_context: RehostingContext):
        runner = BreakpointHandlingRunner(rehosting_context.target)

        boot_patcher = XilinxZynqmpBootPatcher(rehosting_context, enable_optional_patches=True)
        runner.register_handler(boot_patcher)

        secmon_execution_strategy = self._make_call_into_secmon_strategy(rehosting_context)

        secmon_runner = SecMonRunner(runner, secmon_execution_strategy)
        return secmon_runner
