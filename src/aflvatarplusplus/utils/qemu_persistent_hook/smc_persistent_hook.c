#include "../../qemu_mode/qemuafl/qemuafl/api.h"
#include "../../qemu_mode/qemuafl/include/exec/hwaddr.h"

#include <stdio.h>
#include <string.h>

void (*cpu_physical_memory_write)(hwaddr addr, const void *buf, hwaddr len) = NULL;
void (*cpu_physical_memory_read)(hwaddr addr, void *buf, hwaddr len) = NULL;
int (*qemu_log)(const char *fmt, ...) = NULL;

// helper function to set register[idx] = data
// idx must be in range 0 - 6
void set_register_idx(struct arm64_regs *regs, int idx, uint32_t data)	{
        if(idx == 0)   {
        	regs->x0 = data;   
        }
        else if (idx == 1)      {
                regs->x1 = data;
        }
        else if (idx == 2)      {
                regs->x2 = data;
        }
        else if (idx == 3)      {
                regs->x3 = data;
        }
        else if (idx == 4)      {
                regs->x4 = data;
        }
        else if (idx == 5)      {
                regs->x5 = data;
        }
        else if (idx == 6)      {
                regs->x6 = data;
        }
}

// this is an example of a harness for Huawei's eFuse Driver
// manually built but should be possible to synthesize
void huawei_efuse_harness(struct arm64_regs *regs, uint8_t *afl_input_buf, uint32_t input_buf_len)	{
    // Test Harness for Huawei P9/P20 eFuse Driver
    if(input_buf_len >= 0x43)	{

        // x0: const u32
        // use first byte and add to 0xc5000000 -> we only get values between 0xc5000000 - 0xc50000ff
        // we can get the exact values from header files of kernel
        set_register_idx(regs, 0x0, (0xc5000000 + afl_input_buf[0x0]));

        // x1: reference with 0x34a21bff >= x1 >= 0x34a21800 
        // for now just use 0x34a21900
        // there are two locations: first in firmware blob at the beginning of efuse_smc_handler, second
        // in kernel the global struct g_efusec_data is localted at bl31_smem_base + data[0] (0x34A11000 + x)
        // the 0x40 byte size is mostly choosen arbitrary but look at g_efuse_data struct to guess size
        set_register_idx(regs, 0x1, 0x34a21900);
        cpu_physical_memory_write(0x34a21900, &afl_input_buf[0x1], 0x40);

        // x2: const u32 size or length
        // size must be  0x300 >= x2 > 0
        // in kernel in efusec_ioctl the size is calculated by some efuse_mem_attr_xxx
        uint32_t struct_size = (afl_input_buf[0x41] << 8 | afl_input_buf[0x42]) % 0x300;
        set_register_idx(regs, 0x2, struct_size);

        // x3: const uint
        // when called in kernel in efusec_ioctl a constant is passed with 1000 as timeout
        set_register_idx(regs, 0x3, 1000);

        // some hardware emulation for efuse
        // for p20 secmon it is reading 0xfff03004 to wait for efuse
        // at addr 0x35e03270 in func bsp_efuse_read
        uint32_t efuse_state_reg = 0x2;
        cpu_physical_memory_write(0xfff03004, &efuse_state_reg, 0x4);
    }
}

// this is an example of a harness for Huawei's RPMB Driver
// manually built but should be possible to synthesize
void huawei_rpmb_harness(struct arm64_regs *regs, uint8_t *afl_input_buf, uint32_t input_buf_len) {
    // Test Harness for Huawei P9/P20 RPMB Driver
    if (input_buf_len >= 0x2)   {

        // x0: const u32
        // there are three "classes" of funcIDs
        // 0xc6000000 - 0xc6000003  ;  0xc600ff00 - 0xc600ff10  ; 0xc600fff1 - 0xc600fff4
        // use first byte to indicate class and second as offset
        // we can get the exact values from header files of kernel
        if (afl_input_buf[0x0] == 0x0) {
          set_register_idx(regs, 0x0, (0xc6000000 + afl_input_buf[0x1]));
        }
        else if (afl_input_buf[0x0] == 0x1)  {
          set_register_idx(regs, 0x0, (0xc600ff00 + afl_input_buf[0x1]));
        }
        else if (afl_input_buf[0x0] == 0x2)  {
          // here an "overflow" is possible but that should not be relevant
          set_register_idx(regs, 0x0, (0xc600fff0 + afl_input_buf[0x1]));
        }


        // x1: reference starting at 0x34A11000 + offset if RPMB_SVC_REQUEST_ADDR else 0x0
        // if reference just use rest of all bytes provided
        // in firmware blob there is a check for 0x34a29000
        if (regs->x0 == 0xc600FF04)  {
          set_register_idx(regs, 0x1, 0x34a29000);
          cpu_physical_memory_write(0x34a29000, &afl_input_buf[0x2], input_buf_len-0x2);
        }
    }
}

// implementation of a generic harness with the following strategy:
// first byte: bit indicating if subsequent registers hold value (0) or buffer (1)
// starting at second byte: read 0x8 byte if buffer or 0x4 byte if value
// addr of buffers are hardcoded and should be inside NW memory
// size of buffers is hardcoded and is 0x8
// value of each register is 4 byte
void generic_harness(struct arm64_regs *regs, uint8_t *afl_input_buf, uint32_t input_buf_len)	{
  // some address to write afl buf input to
  // this should be somewhere in NW memory
  // make sure this is mapped in QEMU
  uint32_t fuzz_buff_base_addr = 0x490000;
  uint32_t per_buf_size = 0x10000;
  
  // use first byte to indicate either value or buffer for registers
  uint32_t curr_offset = 1;
  int curr_reg_idx = 0;
  // maximal bytes to take from afl input per buffer
  int max_buffer_size = 8;
  
  // read 1 byte chunk from afl stream as long as more is available
  while (curr_offset < input_buf_len && curr_reg_idx < 7)	{
      if((afl_input_buf[0] >> curr_reg_idx & 0x1) == 1)	{
      	// it is a buffer
      	if(input_buf_len >= curr_offset + max_buffer_size)	{
      	   uint32_t location = fuzz_buff_base_addr + (per_buf_size*curr_reg_idx);
      	   set_register_idx(regs, curr_reg_idx, location);
      	   cpu_physical_memory_write(location, &afl_input_buf[curr_offset], max_buffer_size);
      	   curr_offset += max_buffer_size;
      	}
      }
      else	{
      	// it is a value
      	if(input_buf_len >= curr_offset + 4)	{
      	   // read value from afl stream in big endian -> easier human readable
      	   uint32_t afl_data = afl_input_buf[curr_offset] << 24 |
                          afl_input_buf[curr_offset + 1] << 16 |
                          afl_input_buf[curr_offset + 2] << 8 |
                          afl_input_buf[curr_offset + 3];
      	   set_register_idx(regs, curr_reg_idx, afl_data);
      	   curr_offset += 4;
      	}
      }
      curr_reg_idx += 1;
  }
}

// that is currently our master harness
// how afl input input_buf gets injected into the running QEMU instance
// this function is called after each run of QEMU
void afl_persistent_hook(struct arm64_regs *regs, uint64_t guest_base,
                         uint8_t *input_buf, uint32_t input_buf_len) {
        if(input_buf_len >= 1)	{
            // depending on first byte choose harness
        	if(input_buf[0] == 1)	{
        		generic_harness(regs, &input_buf[1], input_buf_len);
        	}
        	else if(input_buf[0] == 2)	{
        		huawei_efuse_harness(regs, &input_buf[1], input_buf_len);
        	}
        	else if(input_buf[0] == 3)	{
        		huawei_rpmb_harness(regs, &input_buf[1], input_buf_len);
        	}
        }
}

// gets called once when hook gets installed
// do we want any functionality for the fuzzer at that time? maybe some setup?
int afl_persistent_hook_init(void (*in_main_func)(), void (*in_main_func_2)(), int (*in_main_func_3)()) {

  cpu_physical_memory_write = in_main_func;
  cpu_physical_memory_read = in_main_func_2;
  qemu_log = in_main_func_3;


  // 1 for shared memory input (faster), 0 for normal input (you have to use
  // read(), input_buf will be NULL)
  qemu_log("INSIDE persistent hook init\n");
  return 1;

}


