"""
Small helper script that prints the GDB register IDs, as received by Avatar2.
These IDs can be used in Architecture classes to tell Avatar2 how to access
specific registers.
"""

import logging
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from typing import Iterable, Type, Tuple

import click
from avatar2 import Avatar, ARM, AARCH64, QemuTarget, Architecture


Registers = Iterable[Tuple[str, int]]


def fetch_register_names_from_avatar2(avatar_arch: Type[Architecture]) -> Registers:
    avatar = Avatar(arch=avatar_arch)

    qemu_target = avatar.add_target(QemuTarget, gdb_port=1357)

    avatar.init_targets()

    register_names = qemu_target.protocols.registers.get_register_names()

    if os.path.isdir(avatar.output_directory):
        shutil.rmtree(avatar.output_directory)

    avatar.shutdown()

    for i, name in enumerate(register_names):
        # v* registers are used for floating point and SIMD in AArch64, the others map to those
        # they use a different size, which we can send to gdb, but gdb does not like registers with a size of 128
        # therefore we skip them
        if re.match(r"[bhsdqv][0-9]+", name):
            print(f"skipping register {name}", file=sys.stderr)
            continue

        yield name, i


def make_gdb_xml(arch: str, registers: Registers):
    target = ET.Element("target")

    architecture = ET.Element("architecture")
    architecture.text = arch
    target.append(architecture)

    feature = ET.Element("feature", attrib={"name": f"org.gnu.gdb.{arch}.core"})

    if arch == "aarch64":
        bitsize = 64
    else:
        raise NotImplementedError("not implemented yet")

    for i, name in registers:
        reg = ET.Element("reg", attrib={"name": name, "bitsize": str(bitsize), "regnum": str(i),})

        if name in ["pc"]:
            reg.attrib["type"] = "data_ptr"

        elif name in ["sp"]:
            reg.attrib["type"] = "code_ptr"

        feature.append(reg)

    target.append(feature)

    return ET.tostring(target).decode()


def make_python_dict(registers: Registers):
    return repr(dict(registers))


@click.command()
@click.argument("arch")
@click.option("--gdb-xml", is_flag=True, default=False)
@click.option("--python-dict", is_flag=True, default=False)
def main(arch: str, gdb_xml: bool, python_dict: bool):
    arch = arch.lower()

    if arch == "arm":
        avatar_arch = ARM
    elif arch == "aarch64":
        avatar_arch = AARCH64
    else:
        print("Unknown architecture:", arch)
        return 1

    # hide all log messages
    logging.basicConfig(level=logging.CRITICAL)

    register_names = fetch_register_names_from_avatar2(avatar_arch)

    if gdb_xml and not python_dict:
        print(make_gdb_xml(arch, register_names))

    elif python_dict and not gdb_xml:
        print(make_python_dict(register_names))

    elif not any([python_dict, gdb_xml]):
        for i, name in enumerate(register_names):
            print(str(i).rjust(3), name)

    else:
        raise RuntimeError("more than one output option provided")


if __name__ == "__main__":
    main()
