#include <qemuafl/api.h>
#include <exec/hwaddr.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>

#define GET_NTH_BIT_MEMORY(address, n) ((*address >> (n) & 0x1))
#define M_PI 3.14159265358979323846

/* ##############   Globals   ############## */
void (*cpu_physical_memory_write)(hwaddr addr, const void *buf, hwaddr len) = NULL;
void (*cpu_physical_memory_read)(hwaddr addr, void *buf, hwaddr len) = NULL;
int (*qemu_log)(const char *fmt, ...) = NULL;

/* EL1 and EL3 shared memory base address and size of buffers.
 * These values are platform specific and might need to be adjusted.
 * `EL1_EL3_SHM_BASE` this phaddr should be normal-world accessible.
 * The phyaddr needs to be backed by volatile memory.
 */
uint32_t EL1_EL3_SHM_BASE = 0x490000;
uint32_t EL1_EL3_SHM_SIZE = 0x10000;
uint64_t max_buffer_size = 16;

typedef struct {
    uint64_t idx;
    uint64_t constant;
    char type[255];
} smcArg;

// make sure this array is big enough to hold CSV data
#define MAX_NUMBER_OF_OPTIONS 1000
smcArg smcArgArray[MAX_NUMBER_OF_OPTIONS][8];
// for each option we have a max of 8 possible smcArgs
// i.e. registers x0 - x7
uint64_t total_smcArg_options = 0;

// stores the addr and size of the buffer provided by afl
// will be set once if a new input is requested
uint8_t *afl_buffer = NULL;
uint64_t afl_buffer_size = 0;
// this variable keeps track of the currently consumed bytes
uint64_t curr_afl_offset = 0;

char *fuzz_logging_path = NULL;

char *print_testcases = NULL;

/**
 * @brief Set register content using the register's index.
 *
 * Helper function to set `register[idx] = data`.
 * `idx` must be in range `0-7`.
 *
 * According to the SMC Calling Convetion: x0-x7 are parameters
 * 
 * @param regs Handle to registers.
 * @param idx  Index of register to be set.
 * @param data Content for the register.
 */
void set_register_idx(struct arm64_regs *regs, int idx, uint64_t data) {
    if (idx == 0) {
        regs->x0 = data;
    } else if (idx == 1) {
        regs->x1 = data;
    } else if (idx == 2) {
        regs->x2 = data;
    } else if (idx == 3) {
        regs->x3 = data;
    } else if (idx == 4) {
        regs->x4 = data;
    } else if (idx == 5) {
        regs->x5 = data;
    } else if (idx == 6) {
        regs->x6 = data;
    } else if (idx == 7) {
        regs->x7 = data;
    }
}

//return number of bytes provided or -1 if non available anymore
int request_afl_data(void *dst_addr, uint64_t size)  {
    if(afl_buffer_size >= curr_afl_offset + size)   {
        memcpy(dst_addr, &afl_buffer[curr_afl_offset], size);
        curr_afl_offset += size;
        return size;
    }
    return -1;
}

// if we look at the SMCCC we can see that the most interesting bytes are
// the first one (will change upper service requested) and especially the lower 4 bit
// and the last two one's will change runtime service
uint32_t mutate_smc_id(uint32_t smc_id) {
    uint32_t ret = smc_id;
    
    uint8_t afl_data1;
    request_afl_data(&afl_data1, sizeof(afl_data1));

    uint16_t afl_data2;
    request_afl_data(&afl_data2, sizeof(afl_data2));

    // upper 4 bit to calc chance
    float chance_of_mutating = (float)(afl_data1 & 0x0F) / 16.0f;
    if(chance_of_mutating >= 0.8f)  {
        // lower 4 bit to mutate
        uint32_t upper_service_value = (afl_data1 & 0xF0) << 20;

        // other two bytes to mutate lower service
        uint32_t lower_service_value = (afl_data2 & 0xFFFF);

        // write values into smc_id
        ret = (smc_id & 0xF0000000) + upper_service_value + ((smc_id & 0x0000FFFF) ^ lower_service_value);
    }
    return ret;
}

// the size can be aligned or not and in shm or not
uint64_t mutate_size(uint64_t size) {
    uint64_t ret = size;
    
    uint8_t afl_data;
    request_afl_data(&afl_data, 1);

    // upper 4 bit to calc chance
    float chance_of_mutating = (float)(afl_data & 0xF) / 16.0f;
    // increasing the chance for mutation here seems to be a good idea
    // as the fuzzer might pass addr/size checks this way
    if(chance_of_mutating >= 0.5f)  {
        if((afl_data & 0x1) == 0x1)   {
            // strip down size to be in shm
            ret = ret % EL1_EL3_SHM_SIZE;
        }
        if((afl_data & 0x1) == 0x2)   {
            // align it
            ret = ret - (ret % 32);
        }
    }
    return ret;
}

/**
 * @brief Parse AFL's input stream and setup VM state accordingly.
 *
 * AFL is providing us with a stream of bytes. We map this stream of bytes to
 * parts of the VM state that we deem worthy to be mutated.
 *
 * Our current strategy for the synthesized harness is the following.
 * First byte: give the index for the smcArgArray
 *
 * @param regs          Handle to VM registers.
 * @param afl_input_buf AFL's input buffer.
 * @param input_buf_len Length of buffer.
 */
void synthesis_harness(struct arm64_regs *regs,
                     uint8_t *afl_input_buf,
                     uint32_t input_buf_len) {
    if(print_testcases != NULL) {
        qemu_log("### NEW TESTCASE ###\n");
        qemu_log("RegIdx,Type,Value,MemValue\n");
    }

    // filter out all inputs which are too small?
    /*if(input_buf_len < 8*max_buffer_size)   {
        if(fuzz_logging != NULL)    {
            FILE* logging_file = fopen("/out/fuzzer_log.log", "a");
            if(logging_file != NULL)    {
                fprintf(logging_file, "-1, ");
                fclose(logging_file);
            }
        // easy way to count: cat fuzzer_log.log | sed 's/\(..\)/\n\1/g' | sort | uniq -c | column
        }
        return;
    }*/

    uint8_t smcArg_idx = 0;
    // first byte indicating used harness option, allows for 255 options
    request_afl_data(&smcArg_idx, sizeof(smcArg_idx));
    smcArg_idx = (smcArg_idx % MAX_NUMBER_OF_OPTIONS) % total_smcArg_options;
    // smcArg_idx will be in bounds of array

    if(fuzz_logging_path != NULL)    {
        FILE* logging_file = fopen(fuzz_logging_path, "a");
        if(logging_file != NULL)    {
            fprintf(logging_file, "%d, ", smcArg_idx);
            fclose(logging_file);
        }
        // easy way to count: cat fuzzer_log.log | sed 's/\(..\)/\n\1/g' | sort | uniq -c | column
    }

    // go through each register idx and check if we can fill it with afl input
    for(uint32_t currIdx = 0; currIdx < 8; currIdx++)  {
        // if we hit a parameter not to be filled just break the loop to save
        // remaining afl bytes for MMIO fuzzing
        if(strcmp(smcArgArray[smcArg_idx][currIdx].type, "donotfill") == 0) {
            break;
        }
        // ensure that the choosen option has the relevant idx
        if(smcArgArray[smcArg_idx][currIdx].idx == currIdx)    {
            // check if we have a constant for that idx
            if(smcArgArray[smcArg_idx][currIdx].constant != UINT64_MAX)	{
                uint64_t tmp_const = smcArgArray[smcArg_idx][currIdx].constant;

                if(currIdx == 0)    {
                    tmp_const = (uint64_t)mutate_smc_id((uint32_t)tmp_const);
                }
                else    {
                    // if not smc id change up the constant
                    uint64_t afl_data = 0;
                    request_afl_data(&afl_data, sizeof(afl_data));
                    tmp_const = tmp_const ^ afl_data;
                }
                set_register_idx(regs, currIdx, tmp_const);
                if(print_testcases != NULL) {
                    qemu_log("%d,const,%lx, \n",currIdx, tmp_const);
                }
            }
            // check if we have type information for that idx
            else if(smcArgArray[smcArg_idx][currIdx].type != NULL && 
                strcmp(smcArgArray[smcArg_idx][currIdx].type, "\n") != 0)	{
                
                // check if it is a memory reference
                if(strstr(smcArgArray[smcArg_idx][currIdx].type, "phys") != NULL ||
                    strstr(smcArgArray[smcArg_idx][currIdx].type, "buf") != NULL ||
                    strstr(smcArgArray[smcArg_idx][currIdx].type, "addr") != NULL ||
                    strstr(smcArgArray[smcArg_idx][currIdx].type, "mem") != NULL)  {
                    // calculate new location for shm
                    uint32_t location = EL1_EL3_SHM_BASE + (EL1_EL3_SHM_SIZE * currIdx);
                    set_register_idx(regs, currIdx, location);
                    uint8_t afl_data[max_buffer_size];
                    memset(afl_data, 0, max_buffer_size);
                    request_afl_data(&afl_data, max_buffer_size);
                    cpu_physical_memory_write(location, &afl_data, max_buffer_size);

                    if(print_testcases != NULL) {
                        qemu_log("%d,memref,%lx,",currIdx, location);
                        for(uint64_t i = 0; i < max_buffer_size; i++)   {
                            qemu_log("%02x", (unsigned char)afl_data[i]);
                        }
                        qemu_log("\n");
                    }
                }
                else if(strstr(smcArgArray[smcArg_idx][currIdx].type, "size") != NULL)  {
                    uint64_t afl_data = 0;
                    request_afl_data(&afl_data, sizeof(afl_data));
                    afl_data = mutate_size(afl_data);
                    set_register_idx(regs, currIdx, afl_data);
                    if(print_testcases != NULL) {
                        qemu_log("%d,const,%lx, \n",currIdx, afl_data);
                    }
                }
                else if(strstr(smcArgArray[smcArg_idx][currIdx].type, "32") != NULL ||
                        strstr(smcArgArray[smcArg_idx][currIdx].type, "int") != NULL)  {
                    uint32_t afl_data = 0;
                    request_afl_data(&afl_data, sizeof(afl_data));
                    set_register_idx(regs, currIdx, afl_data);
                    if(print_testcases != NULL) {
                        qemu_log("%d,const,%lx, \n",currIdx, afl_data);
                    }
                }
                else if(strstr(smcArgArray[smcArg_idx][currIdx].type, "16") != NULL ||
                        strstr(smcArgArray[smcArg_idx][currIdx].type, "short") != NULL)  {
                    uint16_t afl_data = 0;
                    request_afl_data(&afl_data, sizeof(afl_data));
                    set_register_idx(regs, currIdx, afl_data);
                    if(print_testcases != NULL) {
                        qemu_log("%d,const,%lx, \n",currIdx, afl_data);
                    }
                }
                else if(strstr(smcArgArray[smcArg_idx][currIdx].type, "8") != NULL ||
                        strstr(smcArgArray[smcArg_idx][currIdx].type, "char") != NULL)  {
                    uint8_t afl_data = 0;
                    request_afl_data(&afl_data, sizeof(afl_data));
                    set_register_idx(regs, currIdx, afl_data);
                    if(print_testcases != NULL) {
                        qemu_log("%d,const,%lx, \n",currIdx, afl_data);
                    }
                }
                else    {
                    // unknown type just set default
                    if(currIdx == 0)    {
                        uint32_t afl_data = 0;
                        request_afl_data(&afl_data, sizeof(afl_data));
                        set_register_idx(regs, currIdx, afl_data);
                        if(print_testcases != NULL) {
                            qemu_log("%d,const,%lx, \n",currIdx, afl_data);
                        }
                    }
                    else    {
                        uint64_t afl_data = 0;
                        request_afl_data(&afl_data, sizeof(afl_data));
                        set_register_idx(regs, currIdx, afl_data);
                        if(print_testcases != NULL) {
                            qemu_log("%d,const,%lx, \n",currIdx, afl_data);
                        }
                    }
                }
            }
        }
        else    {
            // we land here if there is no entry just set default
            if(currIdx == 0)    {
                uint32_t afl_data = 0;
                request_afl_data(&afl_data, sizeof(afl_data));
                set_register_idx(regs, currIdx, afl_data);
                if(print_testcases != NULL) {
                    qemu_log("%d,const,%lx, \n",currIdx, afl_data);
                }
            }
            else    {
                uint64_t afl_data = 0;
                request_afl_data(&afl_data, sizeof(afl_data));
                set_register_idx(regs, currIdx, afl_data);
                if(print_testcases != NULL) {
                    qemu_log("%d,const,%lx, \n",currIdx, afl_data);
                }
            }
        }
    }
}

/**
 * @brief Prepare the VM for the next fuzzing run.
 *
 * This function is called before each fuzzing run. It is responsible to setup
 * the VM state for the run.
 *
 * @param regs          VM register.
 * @param guest_base    Guest base address.
 * @param input_buf     AFL's input buffer.
 * @param input_buf_len Length of the input buffer.
 */
void afl_persistent_hook(struct arm64_regs *regs, uint64_t guest_base,
                         uint8_t *input_buf, uint32_t input_buf_len) {
    
    afl_buffer = input_buf;
    afl_buffer_size = input_buf_len;
    synthesis_harness(regs, input_buf, input_buf_len);
}

// we read in the results of the previous static analysis
// which fills our SmcArg list with potential harness options
uint64_t read_in_semantics_from_csv(char *pathname)   {
    FILE *fp = NULL;
    int line_max = 255;
    char line[line_max];
    uint64_t currSmcArg = 0;
    unsigned int currIdx = 0;
    
    fp = fopen(pathname, "r");
    if(fp == NULL)  {
        qemu_log("Could not find file...\n");
        exit(EXIT_FAILURE);
    }
    int found_start = 0;
    // read lines until we hit a start
    while(fgets(line, line_max, fp)) {
        if(strstr(line, "BasicBlock") != NULL || found_start == 1)    {
            // for now only take valid smcArgs - meaning we start with X0
            qemu_log(line);
            //fgets(line, line_max, fp);
            //qemu_log(line);
            if(strstr(line, "BasicBlock") != NULL && found_start == 1)  {
                //qemu_log(line);
                // look ahead to check if the next line ends the tuple
                if(currIdx != 0)    {
                    // this fills the remaining idx
                    // instead we can indicate that those are not interesting
                    while(currIdx < 8)  {
                        smcArgArray[currSmcArg][currIdx].idx = currIdx;
                        smcArgArray[currSmcArg][currIdx].constant = UINT64_MAX;
                        strcpy(smcArgArray[currSmcArg][currIdx].type, "donotfill");
                        qemu_log("Added SmcArg idx: %d, const: %llx, type: donotfill\n", currIdx, UINT64_MAX);
                        currIdx += 1;
                    }
                    currSmcArg += 1;
                    qemu_log("SmcArg +=1\n");
                }
                currIdx = 0;
                continue;
            }
            else if (strstr(line, "BasicBlock") == NULL)   {
                // parse in smcArg
                uint64_t idx = strtoul(strtok(line, ","), NULL, 10);
                if(idx == currIdx)  {
                    // TODO: using strtoul with whitespace results in constant 0
                    // maybe we do not want to add that constant here?
                    uint64_t constant = UINT64_MAX;
                    char *c = strtok(NULL, ",");
                    if(c != NULL)   {
                        if(strstr(c, " ") == NULL)   {
                            constant = strtoul(c, NULL, 10);
                        }
                    }
                    smcArgArray[currSmcArg][currIdx].idx = idx;
                    smcArgArray[currSmcArg][currIdx].constant = constant;
                    char *type = strtok(NULL, ",");
                    if(type != NULL)    {
                        strcpy(smcArgArray[currSmcArg][currIdx].type, type);
                    }
                    currIdx += 1;
                    qemu_log("Added SmcArg idx: %d, const: %llx, type: %s\n", idx, constant, type);
                }
            }
            found_start = 1;
        }
    }

    fclose(fp);
    qemu_log("Parsed CSV file!\nTotal of %d potential harness options!\n", currSmcArg);
    return currSmcArg;
}

/**
 * @brief Initialize the afl persistent hook.
 *
 * This function is called once before the start of the fuzzing campaign. It is
 * responsible for any setup needed for the campaign.
 *
 * @param in_main_func    First callback function.
 * @param in_main_func_2  Second callback function.
 * @param in_main_func_3  Third callback function.
 * @return int            Return value.
 */
int afl_persistent_hook_init(void (*in_main_func)(),
                             void (*in_main_func_2)(),
                             int (*in_main_func_3)()) {

    cpu_physical_memory_write = in_main_func;
    cpu_physical_memory_read = in_main_func_2;
    qemu_log = in_main_func_3;

    char *harnessdata = getenv("SMFUZZ_HARNESSDATA_PATH");
    if(harnessdata == NULL)	{
	    harnessdata = (char *)"/in/harnessdata.csv";
    }
    qemu_log("Harnessdata at: %s\n", harnessdata);
    fuzz_logging_path = getenv("SMFUZZ_LOGFILE_PATH");
    if(fuzz_logging_path != NULL)	{
	    qemu_log("Logging active!\n");
    }
    else    {
        qemu_log("Logging inactive!\n");
    }

    print_testcases = getenv("SMFUZZ_PRINT_TESTCASES");

    total_smcArg_options = read_in_semantics_from_csv(harnessdata);

    // 1 for shared memory input (faster), 0 for normal input (you have to use
    // read(), input_buf will be NULL)
    qemu_log("INSIDE persistent hook init\n");

    // TODO: Do we need a return value?
    return 1;
}
