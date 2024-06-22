import os

from avatar2 import AARCH64, Target

from .intelN5x_boot_patcher import IntelN5xBootPatcher
from .intelN5x_call_into_secmon_strategy import IntelN5xCallIntoSecMonStrategyBase
from ..avatar_factory_memory_mapping import AvatarFactoryMemoryMapping
from ..rehosting_context import RehostingContext
from ..secmon_runner import SecMonRunner
from ..structs import Bl31Params, EntryPointInfo, ImageInfo, BlParam
from ...helperScripts import ConvenientAvatar, BreakpointHandlingRunner
from ...helperScripts.colored_register_printer import ColoredRegistersPrinter
from ...helperScripts.keystone import aarch64_asm
from ...helperScripts.target_bridge import DefaultTargetBridge


class SecMonN5xAvatarFactory:

    def __init__(self):
        # virtual hardware configuration
        self._arch = AARCH64
        self._avatar_cpu = "cortex-a53"

        # here our minimal bootloader emulating BL1/2 will take place
        # BL2_BASE taken from platform_def.h in /plat/intel/soc/common/include
        self._entry_address = 0xffe00000

        # start at bl31_entrypoint
        # BL31_BASE taken from platform_def.h in /plat/intel/soc/common/include
        self._secmon_addr = 0x00001000

        # addr where bl params will be added
        self._bl_params_addr = 0x35e80000

        # this is the entrypoint of the TZOS booting sequence "first eret of SM boot"
        # this address can be defined in the bl_params (here an arbitrary address is choosen)
        self._tzos_entry_addr = 0x36200000

        # this is the entrypoint of the rich OS booting "last eret of SM boot"
        # this address can be defined in the bl_params (here an arbitrary address is choosen)
        self._normal_entry_addr = 0x00480000

        # map secure monitor binary here
        # BL31_BASE and BL31_LIMIT
        self.secmon_binary = AvatarFactoryMemoryMapping(0x1000, 0x81000)

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
            mov x1,#0x0
            smc #0
        """

        boot_bin_path = os.path.join(avatar.output_directory, "secure_stub.bin")

        with open(boot_bin_path, "wb") as f:
            f.write(aarch64_asm(secure_stub_code))

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
            mov x14, #{hex(self._secmon_addr)}
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
        avatar.add_memory_range(0x0, 0x1000, name="before_secmon_binary")
        # secmon binary from 0x1000 until 0x81000
        avatar.add_memory_range(0x81000, 0x3FF000, name="after_secmon_binary")
        # normal world entry stub from 0x00480000 until 0x00481000
        avatar.add_memory_range(0x00481000, 0x35D7F000, name="after_normal_stub")
        # secure world stub from 0x36200000 until 0x36201000
        # add MMIO regions or reflected peripheral modeling
        avatar.add_in_memory_buffer_peripheral(0x36201000, 0xC9A01000, name="after_secure_stub")
        avatar.add_pl011(0xffc02000, 0x1000, "uart0", 0)
        avatar.add_memory_range(0xffc03000, 0x1FD000, name="after_uart")
        # bootloader stub from 0xffe00000 until 0xffe01000
        avatar.add_memory_range(0xffe01000, 0x1FF000, name="after_boot_stub")

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
        return IntelN5xCallIntoSecMonStrategyBase(rehosting_context)

    def get_runner(self, rehosting_context: RehostingContext):
        runner = BreakpointHandlingRunner(rehosting_context.target)

        boot_patcher = IntelN5xBootPatcher(rehosting_context)
        runner.register_handler(boot_patcher)

        secmon_execution_strategy = self._make_call_into_secmon_strategy(rehosting_context)

        secmon_runner = SecMonRunner(runner, secmon_execution_strategy)
        return secmon_runner
