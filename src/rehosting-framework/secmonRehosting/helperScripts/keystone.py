from keystone import Ks, KS_ARCH_ARM64, KS_ARCH_ARM, KS_MODE_LITTLE_ENDIAN, KS_MODE_V8, KS_MODE_ARM


def aarch64_asm(code: str):
    """
    Run AArch64 Little Endian assembler on given code.

    :param code: assembler code
    :return: raw assembly in bytes
    """

    ks = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
    assembly, _ = ks.asm(code, as_bytes=True)
    return assembly


def aarch32_asm(code: str):
    """
    Run AArch32 Little Endian assembler on given code.

    :param code: assembler code
    :return: raw assembly in bytes
    """

    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM | KS_MODE_V8)
    assembly, _ = ks.asm(code, as_bytes=True)
    return assembly
