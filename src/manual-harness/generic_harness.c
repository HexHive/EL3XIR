#include <qemuafl/api.h>
#include <exec/hwaddr.h>
#include <stdio.h>
#include <string.h>

#define GET_NTH_BIT_MEMORY(address, n) ((*address >> (n) & 0x1))

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

// stores the addr and size of the buffer provided by afl
// will be set once if a new input is requested
uint8_t *afl_buffer = NULL;
uint64_t afl_buffer_size = 0;
// this variable keeps track of the currently consumed bytes
uint64_t curr_afl_offset = 0;

char *print_testcases = NULL;

/**
 * @brief Set register content using the register's index.
 *
 * Helper function to set `register[idx] = data`.
 * `idx` must be in range `0-5`.
 *
 * @param regs Handle to registers.
 * @param idx  Index of register to be set.
 * @param data Content for the register.
 */
/**
 * According to the SMC Calling Convention, we must use registers as follows if AARCH64:
 *  - Register W0 (32-bit): Function Identifier
 *  - Registers X1-X17 (64-bit): Parameter Registers
 * For the AARCH32 case:
 *  - Register R0: Function Identifier
 *  - Register R1-R7: Parameter Registers
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

/**
 * @brief This is a conceptionally similar harness to the one implemented
 * by partemu. While they try to fuzz TAs, their idea of mapping afl input
 * to parameters and shared memory can be transfered to the SMC interface.
 * 
 * In "optee-userspace/fuzz_ca/teec.c" they define the following fuzz mapping:
 *  Layout of AFL_BUF:
 *  2 bytes type: 1 byte type[0]||type[1], 1 byte type[2]||type[3]
 *  4 bytes cmd
 *  SHM_BUF_SIZE * 4 bytes buffers / values
 * 
 *  Constraints:
 *   type: Each type from TEEC_NONE (0x0) to TEEC_MEMREF_PARTIAL_INOUT (0xF)
 *       types from 0x1 - 0x3: value
 *       types from 0x5 - 0xf: memref
 * 
 * Summary:
 *  - they only populte 4 registers     -> change this to X1-X7
 *  - first 2 byte indicate the types   -> change this to 1 byte as we only differentiate memref/value
 *  - next 4 byte indicate the TA cmd   -> change this to SMC cmd X0
 *  - for memref fixed 16 byte size     -> leave this as is
 * 
 * @param regs          Handle to VM registers.
 * @param afl_input_buf AFL's input buffer.
 * @param input_buf_len Length of buffer.
 */
void partemu_harness(struct arm64_regs *regs,
                     uint8_t *afl_input_buf,
                     uint32_t input_buf_len) {
    if(print_testcases != NULL) {
        qemu_log("### NEW TESTCASE ###\n");
        qemu_log("RegIdx,Type,Value,MemValue\n");
    }

    int reg_idx;
    // for registers X1-X7
    uint8_t param_type[7];
    
    // get the first 4 byte and check types to know how big the input should be
    // TODO: one byte would be enough
    uint32_t afl_types = 0;
    request_afl_data(&afl_types, sizeof(afl_types));
    for (reg_idx = 0; reg_idx < 7; reg_idx++) {
        param_type[reg_idx] = GET_NTH_BIT_MEMORY(afl_input_buf, reg_idx);
    }

    // get next 32-bit value as cmd for the X0 register
    uint32_t smc_id = 0;
    request_afl_data(&smc_id, sizeof(smc_id));
    set_register_idx(regs, 0, smc_id);
    if(print_testcases != NULL) {
        qemu_log("%d,const,%lx, \n",0, smc_id);
    }

    // maximal bytes to take from afl input per buffer
    int max_buffer_size = 16;

    for (reg_idx = 0; reg_idx < 7; reg_idx++) {
        switch (param_type[reg_idx]) {
            case 0x1:;
                // value - just copy 8 byte into xn register
                uint64_t value = 0;
                request_afl_data(&value, sizeof(value));
                // write to register idx +1 because parameters start at X1
                set_register_idx(regs, reg_idx+1, value);
                if(print_testcases != NULL) {
                    qemu_log("%d,const,%lx, \n",reg_idx+1, value);
                }
                break;
            case 0x0:;
                // memref - take a fitting current NW address and put 'max_buffer_size'
                // bytes into it
                uint8_t afl_data[max_buffer_size];
                memset(afl_data, 0, max_buffer_size);
                int ret = request_afl_data(&afl_data, max_buffer_size);
                uint64_t location = EL1_EL3_SHM_BASE + (EL1_EL3_SHM_SIZE * reg_idx);
                if(ret != -1)   {
                    set_register_idx(regs, reg_idx+1, location);
                    cpu_physical_memory_write(location, &afl_data,
                                          max_buffer_size);
                }
                if(print_testcases != NULL) {
                    qemu_log("%d,memref,%lx,",reg_idx+1, location);
                    for(uint64_t i = 0; i < max_buffer_size; i++)   {
                        qemu_log("%02x", (unsigned char)afl_data[i]);
                    }
                    qemu_log("\n");
                }
        }
    }
}

/**
 * @brief Parse AFL's input stream and setup VM state accordingly.
 *
 * AFL is providing us with a stream of bytes. We map this stream of bytes to
 * parts of the VM state that we deem worthy to be mutated.
 *
 * Our current (naive) strategy is the following.
 * First byte: bit indicating if subsequent registers hold value (0) or
 * buffer (1).
 * From second byte: read 0x8 byte if buffer or 0x4 byte if value.
 * `addr` of buffers are hardcoded and should be inside NW memory.
 * `size` of buffers are hardcoded and 0x8 byte.
 * `value` of each register is 4 byte.
 *
 * @param regs          Handle to VM registers.
 * @param afl_input_buf AFL's input buffer.
 * @param input_buf_len Length of buffer.
 */
void generic_harness(struct arm64_regs *regs,
                     uint8_t *afl_input_buf,
                     uint32_t input_buf_len) {
    // use first byte to indicate either value or buffer for registers
    uint32_t curr_offset = 1;
    int curr_reg_idx = 0;
    // maximal bytes to take from afl input per buffer
    int max_buffer_size = 8;

    // read 1 byte chunk from afl stream as long as more is available
    while (curr_offset < input_buf_len && curr_reg_idx < 6) {
        if ((afl_input_buf[0] >> curr_reg_idx & 0x1) == 1) {
            // it is a buffer
            if (input_buf_len >= curr_offset + max_buffer_size) {
                uint32_t location = EL1_EL3_SHM_BASE
                                    + (EL1_EL3_SHM_SIZE * curr_reg_idx);
                set_register_idx(regs, curr_reg_idx, location);
                cpu_physical_memory_write(location, &afl_input_buf[curr_offset],
                                          max_buffer_size);
                curr_offset += max_buffer_size;
            }
        } else {
            // it is a value
            if (input_buf_len >= curr_offset + 4) {
                // read value from afl stream in big endian
                // -> easier human readable
                uint32_t afl_data = afl_input_buf[curr_offset] << 24
                                    | afl_input_buf[curr_offset + 1] << 16
                                    | afl_input_buf[curr_offset + 2] << 8
                                    | afl_input_buf[curr_offset + 3];
                set_register_idx(regs, curr_reg_idx, afl_data);
                curr_offset += 4;
            }
        }
        curr_reg_idx += 1;
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
    //generic_harness(regs, input_buf, input_buf_len);
    partemu_harness(regs, input_buf, input_buf_len);
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
    // TODO: do we want any functionality for the fuzzer at that time?
    //       maybe some setup?
    cpu_physical_memory_write = in_main_func;
    cpu_physical_memory_read = in_main_func_2;
    qemu_log = in_main_func_3;

    print_testcases = getenv("SMFUZZ_PRINT_TESTCASES");

    // 1 for shared memory input (faster), 0 for normal input (you have to use
    // read(), input_buf will be NULL)
    qemu_log("INSIDE persistent hook init\n");

    // TODO: Do we need a return value?
    return 1;
}
