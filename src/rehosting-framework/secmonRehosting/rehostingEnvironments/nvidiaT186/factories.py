import os

from avatar2 import AARCH64, Target

from .nvidiaT186_boot_patcher import NvidiaT186BootPatcher
from .nvidiaT186_call_into_secmon_strategy import NvidiaT186CallIntoSecMonStrategyBase
from ..avatar_factory_memory_mapping import AvatarFactoryMemoryMapping
from ..rehosting_context import RehostingContext
from ..secmon_runner import SecMonRunner
from ..structs import Bl31Params, EntryPointInfo, ImageInfo, BlParam
from ...helperScripts import ConvenientAvatar, BreakpointHandlingRunner
from ...helperScripts.colored_register_printer import ColoredRegistersPrinter
from ...helperScripts.keystone import aarch64_asm
from ...helperScripts.target_bridge import DefaultTargetBridge


class SecMonT186AvatarFactory:

    def __init__(self):
        # virtual hardware configuration
        self._arch = AARCH64
        self._avatar_cpu = "cortex-a53"

        # here our minimal bootloader emulating BL1/2 will take place
        self._entry_address = 0x00001000

        # start at bl31_entrypoint
        # TEGRA_TZRAM_BASE taken from tegra_def.h in /plat/nvidia/tegra/include/t186/
        self._secmon_addr = 0x30000000

        # addr where bl params will be written
        # somewhere directly after the bootloader stub
        self._bl_params_addr = 0x2000

        # this is the entrypoint of the TZOS booting sequence "first eret of SM boot"
        # this address can be defined in the bl_params (here an arbitrary address is choosen)
        self._tzos_entry_addr = 0x60000000

        # this is the entrypoint of the rich OS booting "last eret of SM boot"
        # this address can be defined in the bl_params
        # taken from TEGRA_DRAM_BASE
        self._normal_entry_addr = 0x80000000

        # map secure monitor binary here
        # TEGRA_TZRAM_SIZE used as size
        self.secmon_binary = AvatarFactoryMemoryMapping(0x30000000, 0x40000)

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
        bl32_size = 0x00001000
        bl33_base = 0x80000000
        bl33_size = 0x00001000
        
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

        # 
        bl_list["bl31_params"] = BlParam(
            base_addr,
            Bl31Params(
                1234,                           # bl31_image_info - should not matter
                bl_list["bl32_ep"].addr,        # bl32_ep_info
                bl_list["bl32_image"].addr,     # bl32_image_info
                bl_list["bl33_ep"].addr,        # bl33_ep_info
                bl_list["bl33_image"].addr,     # bl33_image_info
            ),
        )
        # glue everything together
        bl_params = (
                bl_list["bl31_params"].structure.to_bytes()
                + bl_list["bl32_ep"].structure.to_bytes()
                + bl_list["bl33_ep"].structure.to_bytes()
                + bl_list["bl32_image"].structure.to_bytes()
                + bl_list["bl33_image"].structure.to_bytes()
        )

        target.write_memory(base_addr, len(bl_params), bl_params, raw=True)

        # write any platform specific parameter from bl2 into memory
        plat_param_base = 0x3000
        """
        typedef struct plat_params_from_bl2 {
	        /* TZ memory size */
	        uint64_t tzdram_size;
	        /* TZ memory base */
	        uint64_t tzdram_base;
	        /* UART port ID */
	        int32_t uart_id;
	        /* L2 ECC parity protection disable flag */
	        int32_t l2_ecc_parity_prot_dis;
	        /* SHMEM base address for storing the boot logs */
	        uint64_t boot_profiler_shmem_base;
	        /* System Suspend Entry Firmware size */
	        uint64_t sc7entry_fw_size;
	        /* System Suspend Entry Firmware base address */
	        uint64_t sc7entry_fw_base;
	        /* Enable dual execution */
	        uint8_t enable_ccplex_lock_step;
        } plat_params_from_bl2_t;
        """
        # tz memory size 
        target.write_memory(plat_param_base, 8, 0x40000)
        # tz memory base 
        target.write_memory(plat_param_base + 8, 8, 0x30000000)
        # uart port id
        target.write_memory(plat_param_base + 16, 4, 0x0)
        # ecc_parity
        target.write_memory(plat_param_base + 20, 4, 0x0)
        # shmem for boot log - must be NW
        target.write_memory(plat_param_base + 24, 8, 0x80001000)
    
        

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
        # 0x1000 - 0x2000 bootloader stub
        # 0x2000 - 0x4000 bootloader params written into memory
        avatar.add_memory_range(0x2000, 0x2000, name="after_bootloader")
        avatar.add_in_memory_buffer_peripheral(0x4000, 0x2fffc000, name="after_bootloader_params")
        # 0x30000000 - 0x30040000 secmon binary
        # add MMIO regions or reflected peripheral modeling
        avatar.add_in_memory_buffer_peripheral(0x30040000, 0x2ffc0000, name="after_secmon")
        # 0x60000000 - 0x60001000 SW stub
        avatar.add_memory_range(0x60001000, 0x1ffff000, name="after_tzos")
        # 0x80000000 - 0x80001000 NW stub
        avatar.add_memory_range(0x80001000, 0x7ffff000, name="after_nw")

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
        return NvidiaT186CallIntoSecMonStrategyBase(rehosting_context)

    def get_runner(self, rehosting_context: RehostingContext):
        runner = BreakpointHandlingRunner(rehosting_context.target)

        boot_patcher = NvidiaT186BootPatcher(rehosting_context, enable_optional_patches=True)
        runner.register_handler(boot_patcher)

        secmon_execution_strategy = self._make_call_into_secmon_strategy(rehosting_context)

        secmon_runner = SecMonRunner(runner, secmon_execution_strategy)
        return secmon_runner
