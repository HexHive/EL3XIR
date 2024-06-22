#!/usr/bin/env python3
import argparse
import os
import subprocess
import time

def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="")
    parser.add_argument("cpus", help="")
    parser.add_argument("in_dir", help="")
    parser.add_argument("out_dir", help="")

    return parser

def main():

    arg_parser = setup_args()
    args = arg_parser.parse_args()

    cpuids = int(args.cpus, 10)

    smc_ranges = [
        (0x80000000, 0x8000FFFF),       # SMC32 Arm Architecture Calls
        (0x81000000, 0x8100FFFF),       # SMC32 CPU Service Calls
        (0x82000000, 0x8200FFFF),       # SMC32 SiP Service Calls
        (0x83000000, 0x8300FFFF),       # SMC32 OEM Service Calls
        (0x84000000, 0x8400FFFF),       # SMC32 Standard Service Calls
        #(0x85000000, 0x8500FFFF),      # SMC32 Standard Hypervisor Service Calls
        #(0x86000000, 0x8600FFFF),      # SMC32 Vendor Specific Hypervisor Service Calls
        #(0x87000000, 0xAF00FFFF),      # Reserved for future expansion
        #(0xB0000000, 0xB100FFFF),       # SMC32 Trusted Application Calls
        #(0xB2000000, 0xBF00FFFF),       # SMC32 Trusted OS Calls
        (0xC0000000, 0xC000FFFF),       # SMC64 Arm Architecture Calls
        (0xC1000000, 0xC100FFFF),       # SMC64 CPU Service Calls
        (0xC2000000, 0xC200FFFF),       # SMC64 SiP Service Calls
        (0xC3000000, 0xC300FFFF),       # SMC64 OEM Service Calls
        (0xC4000000, 0xC400FFFF),       # SMC64 Standard Service Calls
        #(0xC5000000, 0xC500FFFF),       # SMC64 Standard Hypervisor Service Calls
        #(0xC6000000, 0xC600FFFF),       # SMC64 Vendor Specific Hypervisor Calls
        #(0xC7000000, 0xEF00FFFF),       # Reserved for future expansion
        #(0xF0000000, 0xF100FFFF),       # SMC64 Trusted Application Calls
        #(0xF2000000, 0xFF00FFFF),       # SMC64 Trusted OS Calls
    ]
    
    # run all testcases defined in the smc ranges in parallel
    for i in range(len(smc_ranges)):
        curr_container_name = "el3xir-probe-{}".format(i % cpuids)
        print(curr_container_name)
        # check if container is currently running and wait
        while True:
            check_cmd = ["docker", "ps", "--format", "{{.Names}}"]
            container_names = subprocess.check_output(check_cmd).decode().strip().split("\n")
            print("Running Containers: {}".format(container_names))
            if curr_container_name not in container_names:
                break
            time.sleep(5)

        odir = args.out_dir + "/" + str(i % cpuids) + "/"
        docker_cmd = "IN={} OUT={} CPUSET={} docker compose run --name el3xir-probe-{} -d --rm el3xir-runner /probe-funcIDs.sh {} {} {}".format(
        args.in_dir, odir, i % cpuids, i % cpuids, args.target, smc_ranges[i][0], smc_ranges[i][1])
        print(docker_cmd)
        # wait for container to start up - using sleep is not the best way but works for now
        time.sleep(5)

        p = subprocess.Popen(docker_cmd, env=os.environ.copy(), shell=True)

    # wait for all docker containers to finish
    while True:
        curr_container_name = "el3xir-probe"
        check_cmd = ["docker", "ps", "--format", "{{.Names}}"]
        container_names = subprocess.check_output(check_cmd).decode().strip().split("\n")
        print("Running Containers: {}".format(container_names))
        
        found = False
        for c in container_names:
            if curr_container_name in c:
                found = True
        if found == False:
            break
        time.sleep(5)
    time.sleep(3)
    # number of tuples without an SMC id
    smc_id_less_tuple = 0
    # number of tuples with duplicate SMC ids
    smc_id_duplicates = 0
    # number of tuples overall
    static_total = 0
    # content to write
    new_harnessdata = []
    # indicate if current tuple is good
    copytuple = 0
    currBB = ""
    # open up harnessdata and extract funcIDs
    static_rservices = []
    with open(args.in_dir + "/harnessdata.csv", "r") as f:
        ll = f.readlines()
        for l in ll:
            if  "BasicBlock: Probing" in l:
                break
            elif "BasicBlock:..." in l:
                currBB = l
                copytuple = 1
                new_harnessdata.append(l)
            elif "BasicBlock:" in l:
                currBB = l
                copytuple = 0
                static_total += 1
            elif copytuple == 1:
                new_harnessdata.append(l)
            try:
                line = l.split(",")[0]
                if "0" == line:
                    try:
                        value = hex(int(l.split(",")[1], 10))
                        if value not in static_rservices:
                            static_rservices.append(value)
                        else:
                            smc_id_duplicates += 1
                        copytuple = 1
                        new_harnessdata.append(currBB)
                        new_harnessdata.append(l)
                    except ValueError:
                        smc_id_less_tuple += 1
            except IndexError:
                # ignore non-fitting lines
                pass

    # keymap to save all unique fingerprints and their associated list of funcIDs
    fp_to_ids = {}

    for i in range(cpuids):
        odir = args.out_dir + "/" + str(i % cpuids) + "/" + "afl-edges-probe-out/"

        # go through all out directories holding the cov files
        for fi in os.listdir(odir):
            fp = 0
            funcid = int(fi.split("-")[-1], 16)
            with open(odir + fi, "r") as f:
                ls = f.readlines()
                for l in ls:
                    values = l.split("\n")[0].split(":")
                    fp += int(values[0], 10) * int(values[1], 10)
            if fp not in fp_to_ids:
                fp_to_ids[fp] = [hex(funcid)]
            else:
                fp_to_ids[fp].append(hex(funcid))

    # sort keymap from most entries to least
    sorted_fp_to_ids = sorted(fp_to_ids.items(), key=lambda x: len(x[1]), reverse=True)
    
    # write results into a file
    resultfile = args.out_dir + "/synth-summary-{}.txt".format(args.target)
    probe_result_file = open(resultfile, "w")

    # count funcIDs with unique fingerprints -> those are probably backed by a runtime service
    rservices = []
    new_rservices = []

    for j in range(len(sorted_fp_to_ids)):
        #probe_result_file.write("\n##########################\n")
        #probe_result_file.write("Number of funcIDs: " + str(len(sorted_fp_to_ids[j][1]))  + "\n")
        #probe_result_file.write(str(sorted_fp_to_ids[j][1]))
        if len(sorted_fp_to_ids[j][1]) <= 2:
            for i in sorted_fp_to_ids[j][1]:
                rservices.append(i)
                if i not in static_rservices:
                    new_rservices.append(i)

    probe_result_file.write("\n########## PROBING ##########\n")
    probe_result_file.write("\ntotal number of unique fingerprints found: " + str(len(sorted_fp_to_ids)))
    probe_result_file.write("\ntotal number of runtime services found by probing (only max two funcIDs with same fingerprint): "
                            + str(len(rservices)) + "\n")
    #probe_result_file.write(str(rservices))

    probe_result_file.write("\n########## STATIC ANALYSIS / INTERFACE RECOVERY ##########\n")
    probe_result_file.write("\ntotal number of candidate tuples: " + str(static_total))
    #probe_result_file.write("\ntotal number of unique static runtime services found: " + str(len(static_rservices)) + "\n")
    #probe_result_file.write(str(static_rservices))
    probe_result_file.write("\ntotal number of smc_id duplicate tuples (may also include wrong smc_id): " + str(smc_id_duplicates))
    probe_result_file.write("\ntotal number of tuples without smc_id: " + str(smc_id_less_tuple))

    probe_result_file.write("\n\n########## COMPARISON ##########\n")
    probe_result_file.write("\ntotal number of new runtime services found by probing compared to static analysis: " + str(len(new_rservices)))
    #probe_result_file.write(str(new_rservices))

    probe_result_file.write("\ntotal number of unique runtime services found overall (static analysis + probing) combined: " + str(len(new_rservices) + len(static_rservices)))
    probe_result_file.write("\ntotal number of tuples overall (static analysis + probing): " + str(static_total + len(new_rservices)) + "\n")

    probe_result_file.close()

    # write pruned harnessdata and new probing funcIDs
    with open(args.in_dir + "/harnessdata.csv", "w") as f:
        f.write("".join(new_harnessdata))
        for funcID in new_rservices:
            # first write basic block
            f.write("BasicBlock: Probing\n")
            f.write("0,{},\n".format(int(funcID, 16)))
            for i in range(1,8):
                f.write("{}, ,u64\n".format(i))

if __name__ == '__main__':
    main()
