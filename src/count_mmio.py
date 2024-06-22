#!/usr/bin/env python3
import argparse

def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="")
    parser.add_argument("infile", help="")

    return parser

def main():

    arg_parser = setup_args()
    args = arg_parser.parse_args()

    hook_addr = 0
    if args.target == "intel-n5x":
        hook_addr =0x0000bc00
    elif args.target == "nxp-imx8mq":
        hook_addr =0x00918c04
    elif args.target == "xilinx-zynqmp":
        hook_addr =0xffff1c00
    elif args.target == "nvidia-t186":
        hook_addr =0x3000dc00
    else:
        print("Unknown target selected...")
        exit(-1)
    

    seen_mmio_registers = {}
    seen_mmio_values = []
    seen_bb_pc_with_mmio = []
    seen_funcids_with_mmio = []

    with open(args.infile, "r") as f:
        ll = f.readlines()
        last_seen_pc = 0
        last_seen_funcID = 0
        for l in ll:
            if "PC=" in l:
                if last_seen_pc == hook_addr:
                    last_seen_funcID = int(l.split("X00=")[1].split(" ")[0], 16)
                last_seen_pc = int(l.split("PC=")[1].split(" ")[0], 16)
                #print(l)
                #print(last_seen_pc)
            if "MMIO fuzz" in l:
                #print(l)
                mmio_register = int(l.split("from addr: ")[1].split(" return")[0], 16)
                #if mmio_register not in seen_mmio_registers:
                #    seen_mmio_registers.append(mmio_register)
                try:
                    seen_mmio_registers[mmio_register] += 1
                except KeyError:
                    seen_mmio_registers[mmio_register] = 1
                if last_seen_pc not in seen_bb_pc_with_mmio:
                    seen_bb_pc_with_mmio.append(last_seen_pc)
                if last_seen_funcID not in seen_funcids_with_mmio:
                    seen_funcids_with_mmio.append(last_seen_funcID)
                
                mmio_value = int(l.split("return value: ")[1].split("!")[0], 16)
                if mmio_value not in seen_mmio_values:
                    seen_mmio_values.append(mmio_value)

    mmio_reglist = list(seen_mmio_registers.items())

    sorted_mmio_reglist = sorted(mmio_reglist, key=lambda x: x[1])

    mmio_regs_over_limit = 0
    print("########## LIST OF MMIO REGISTER ADDRESSES AND NUMBER OF ACCESSES ##########\n")
    for i in sorted_mmio_reglist:
        if i[1] > 10:
            mmio_regs_over_limit += 1
        print(f'{hex(i[0])}: {i[1]}')

    seen_bb_pc_with_mmio.sort()
    print("\n########## LIST OF BASIC BLOCK ADDRESSES OF MMIO ACCESSES ##########\n")
    print(list(map(hex, seen_bb_pc_with_mmio)))

    seen_funcids_with_mmio.sort()
    print("\n########## LIST OF FUNCTION IDENTIFIERS AFFECTED BY MMIO ACCESSES ##########\n")
    print(list(map(hex, seen_funcids_with_mmio)))

    print("\n########## SUMMARY REFLECTED PERIPHERAL MODELING ##########\n")
    print("Total of " + str(len(seen_mmio_registers)) + " unique MMIO registers modeled!")
    print("Total of " + str(mmio_regs_over_limit) + " MMIO registers used more than 10 times!")
    print("Total of " + str(len(seen_bb_pc_with_mmio)) + " unique BBs with MMIO access!")
    print("Total of " + str(len(seen_funcids_with_mmio)) + " unique FuncIDs/runtime services affected by MMIO accesses!")
    print("Total of " + str(len(seen_mmio_values)) + " unique MMIO values returned!\n")

if __name__ == '__main__':
    main()