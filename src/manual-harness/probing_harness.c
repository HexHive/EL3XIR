#include <qemuafl/api.h>
#include <exec/hwaddr.h>
#include <stdio.h>
#include <string.h>

/* ##############   Globals   ############## */
int (*qemu_log)(const char *fmt, ...) = NULL;

// stores the addr and size of the buffer provided by afl
// will be set once if a new input is requested
uint8_t *afl_buffer = NULL;
uint64_t afl_buffer_size = 0;
// this variable keeps track of the currently consumed bytes
uint64_t curr_afl_offset = 0;

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
*
 * @param regs          Handle to VM registers.
 * @param afl_input_buf AFL's input buffer.
 * @param input_buf_len Length of buffer.
 */
void probing_harness(struct arm64_regs *regs,
                     uint8_t *afl_input_buf,
                     uint32_t input_buf_len) {
    // get 32-bit value as funcID for the X0 register
    uint64_t funcID = 0;
    memcpy(&funcID, &afl_buffer[0], sizeof(uint32_t));
    //qemu_log("Probing funcID: %lx\n", funcID);
    regs->x0 = funcID;
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
    probing_harness(regs, input_buf, input_buf_len);
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
    qemu_log = in_main_func_3;

    return 1;
}
