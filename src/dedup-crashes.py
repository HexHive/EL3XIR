#!/usr/bin/env python3
import argparse

def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("qemu_logfile", help="logging file of qemu containing multiple testcases")

    return parser

def main():
    arg_parser = setup_args()
    args = arg_parser.parse_args()

    logfile = open(args.qemu_logfile, "r")
    logfile_list = logfile.readlines()

    unique_crashes = []
    unique_total = 0
    curr_crash_log = []
    curr_register_input = []
    print_testcase = 0
    curr_testcase = ""
    for l in logfile_list:
        if print_testcase == 1:
            curr_testcase += l
        if "### NEW TESTCASE ###" in l:
            print_testcase = 1
        if "----------------" in l:
            print_testcase = 0
        if "Trace" in l:
            curr_crash_log.append(l.split("[")[-1])
        if "AFL DATA/PREFETCH" in l:
            if curr_crash_log not in unique_crashes:
                unique_crashes.append(curr_crash_log)
                print("Test Case:")
                print(curr_testcase)
                print(curr_crash_log)
                unique_total += 1
                print(f"Total unique crashes: {unique_total}\n")
            curr_crash_log = []
            curr_testcase = ""

if __name__ == '__main__':
    main()
