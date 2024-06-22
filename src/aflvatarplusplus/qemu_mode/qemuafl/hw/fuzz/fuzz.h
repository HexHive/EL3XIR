#ifndef HW_FUZZ_H
#define HW_FUZZ_H

#include "hw/sysbus.h"
#include "qom/object.h"

#define TYPE_FUZZ "FUZZ"

typedef struct brState brState;
DECLARE_INSTANCE_CHECKER(brState, FUZZ, TYPE_FUZZ)

struct brState
{
    MemoryRegion mmio;
    unsigned char butterReg[6]; //{'B','U','T','T','E','R'};
};

brState *br_create(MemoryRegion *address_space, hwaddr base);

#endif //HW_FUZZ_H


