/*
 * Avatar2 configurable machine for dynamic creation of emulated boards
 *
 * Copyright (C) 2017 Eurecom
 * Written by Dario Nisi, Marius Muench & Jonas Zaddach
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
 * for more details.
 *
 * This code is derived from versatilepb.c:
 *   ARM Versatile Platform/Application Baseboard System emulation.
 *   Copyright (c) 2005-2007 CodeSourcery.
 *   Written by Paul Brook
 */

//general imports
#include "qemu/osdep.h"
#include "sysemu/sysemu.h"
#include "exec/address-spaces.h"
#include "hw/hw.h"
#include "hw/irq.h"
#include "hw/sysbus.h"
#include "hw/boards.h"
#include "hw/qdev-properties.h"

//plattform specific imports
#ifdef TARGET_ARM
#include "target/arm/cpu.h"
#include "hw/arm/armv7m.h"
#include "hw/avatar/arm_helper.h"
#endif

#ifdef TARGET_AARCH64
// TODO: revise this list -- might not be complete for aarch64
#include "hw/intc/arm_gic.h"
#endif

#ifdef TARGET_MIPS
#include "hw/mips/mips.h"
#include "hw/mips/cpudevs.h"
#include "target/mips/cpu.h"
#endif

//qapi imports
#include "qapi/error.h"
#include "qapi/qmp/qjson.h"
#include "qapi/qmp/qobject.h"
#include "qapi/qmp/qnum.h"
#include "qapi/qmp/qdict.h"
#include "qapi/qmp/qlist.h"

// for some reason GLib functionality is used in hw/avatar2
#include "glib-2.0/glib.h"


//AFL dependencies
#include "qemuafl/common.h"
#include "hw/fuzz/fuzz.h"

#define QDICT_ASSERT_KEY_TYPE(_dict, _key, _type) \
    g_assert(qdict_haskey(_dict, _key) && qobject_type(qdict_get(_dict, _key)) == _type)

#define RAM_RESIZEABLE (1 << 2)
/* Board init.  */

static QDict * load_configuration(const char * filename)
{
    // the filename passed is the one initially passed via -kernel
    int file = open(filename, O_RDONLY);

    if (file < 0) {
        fprintf(stderr, "Error: configuration file not found: %s\n", filename);
        exit(1);
    }

    off_t filesize = lseek(file, 0, SEEK_END);
    char * filedata = NULL;
    ssize_t err;
    Error * qerr = NULL;
    QObject * obj;
    QDict * obj_dict;

    lseek(file, 0, SEEK_SET);

    filedata = g_malloc(filesize + 1);
    memset(filedata, 0, filesize + 1);

    if (!filedata)
    {
        fprintf(stderr, "%ld\n", filesize);
        fprintf(stderr, "Out of memory\n");
        exit(1);
    }

    err = read(file, filedata, filesize);

    if (err != filesize)
    {
        fprintf(stderr, "Reading configuration file failed\n");
        exit(1);
    }

    close(file);

    obj = qobject_from_json(filedata, &qerr);
    if (!obj || qobject_type(obj) != QTYPE_QDICT)
    {
        fprintf(stderr, "Error parsing JSON configuration file\n");
        exit(1);
    }

    obj_dict = qobject_to(QDict, obj);
    if (!obj_dict) {
        qobject_unref(obj);
        fprintf(stderr, "Invalid JSON object given");
        exit(1);
    }

    g_free(filedata);

    return obj_dict;
}

static QDict *peripherals;

static void set_properties(DeviceState *dev, QList *properties)
{
    QListEntry *entry;
    QLIST_FOREACH_ENTRY(properties, entry)
    {
        QDict *property;
        const char *name;
        const char *type;

        g_assert(qobject_type(entry->value) == QTYPE_QDICT);

        property = qobject_to(QDict, entry->value);
        QDICT_ASSERT_KEY_TYPE(property, "type", QTYPE_QSTRING);
        QDICT_ASSERT_KEY_TYPE(property, "name", QTYPE_QSTRING);

        name = qdict_get_str(property, "name");
        type = qdict_get_str(property, "type");

        if(!strcmp(type, "serial"))
        {
            QDICT_ASSERT_KEY_TYPE(property, "value", QTYPE_QNUM);
            const int value = qdict_get_int(property, "value");
            qdev_prop_set_chr(dev, name, serial_hd(value));
        }
        else if(!strcmp(type, "string"))
        {
            QDICT_ASSERT_KEY_TYPE(property, "value", QTYPE_QSTRING);
            const char *value = qdict_get_str(property, "value");
            qdev_prop_set_string(dev, name, value);
        }
        else if(!strcmp(type, "int32"))
        {
            QDICT_ASSERT_KEY_TYPE(property, "value", QTYPE_QNUM);
            const int value = qdict_get_int(property, "value");
            qdev_prop_set_int32(dev, name, value);
        }
        else if(!strcmp(type, "uint32"))
        {
            QDICT_ASSERT_KEY_TYPE(property, "value", QTYPE_QNUM);
            const int value = qdict_get_int(property, "value");
            qdev_prop_set_uint32(dev, name, value);
        }
        else if(!strcmp(type, "int64"))
        {
            QDICT_ASSERT_KEY_TYPE(property, "value", QTYPE_QNUM);
            const int64_t value = qdict_get_int(property, "value");
            qdev_prop_set_uint64(dev, name, value);
        }
        else if(!strcmp(type, "uint64"))
        {
            QDICT_ASSERT_KEY_TYPE(property, "value", QTYPE_QNUM);
            const uint64_t value = qdict_get_int(property, "value");
            qdev_prop_set_uint64(dev, name, value);
        }
        else if(!strcmp(type, "device"))
        {
            QDICT_ASSERT_KEY_TYPE(property, "value", QTYPE_QSTRING);
            const char *value = qdict_get_str(property, "value");
            QObject *pr = qdict_get(peripherals, value);
            qdev_prop_set_chr(dev, name, (void *) pr);
        }
    }
}

static void dummy_interrupt(void *opaque, int irq, int level)
{}

static SysBusDevice *make_configurable_device(const char *qemu_name,
                                              uint64_t address,
                                              QList *properties)
{
    DeviceState *dev;
    BusState* sysbus;
    SysBusDevice *s;
    qemu_irq irq;

    sysbus = sysbus_get_default();
    /* replace the result of: dev = qdev_create(NULL, qemu_name); */

    dev = qdev_new(qemu_name);
    
    /* this is a sysbus device. 
     * QEMU no longer attaches devices to this automatically; 
     * we will need to give it a helping hand. */
    //qdev_set_parent_bus(dev, sysbus);
    //dev->realized = true;
    if(properties) set_properties(dev, properties);

    qdev_realize_and_unref(dev, sysbus, NULL);

    s = SYS_BUS_DEVICE(dev);
    sysbus_mmio_map(s, 0, address);
    irq = qemu_allocate_irq(dummy_interrupt, dev, 1);
    sysbus_connect_irq(s, 0, irq);

    return s;
}

static off_t get_file_size(const char * path)
{
    struct stat stats;

    if (stat(path, &stats))
    {
        printf("ERROR: Getting file size for file %s\n", path);
        return 0;
    }

    return stats.st_size;
}

static int is_absolute_path(const char * filename)
{
    return filename[0] == '/';
}

static int get_dirname_len(const char * filename)
{
    int i;

    for (i = strlen(filename) - 1; i >= 0; i--)
    {
        //FIXME: This is only Linux-compatible ...
        if (filename[i] == '/')
        {
            return i + 1;
        }
    }

    return 0;
}

static void init_memory_area(QDict *mapping, const char *kernel_filename)
{
    uint64_t size;
    uint64_t data_size;
    char * data = NULL;
    const char * name;
    MemoryRegion * ram;
    uint64_t address;
    int is_rom;
    MemoryRegion *sysmem = get_system_memory();

    QDICT_ASSERT_KEY_TYPE(mapping, "name", QTYPE_QSTRING);
    QDICT_ASSERT_KEY_TYPE(mapping, "size", QTYPE_QNUM);
    // g_assert((qdict_get_int(mapping, "size") & ((1 << 12) - 1)) == 0);

    if(qdict_haskey(mapping, "is_rom")) {
        QDICT_ASSERT_KEY_TYPE(mapping, "is_rom", QTYPE_QBOOL);
    }

    name = qdict_get_str(mapping, "name");
    is_rom = qdict_haskey(mapping, "is_rom")
          && qdict_get_bool(mapping, "is_rom");
    size = qdict_get_uint(mapping, "size");

    ram =  g_new(MemoryRegion, 1);
    g_assert(ram);

    if(!is_rom)
    {
        memory_region_init_ram(ram, NULL, name, size, &error_fatal);
    } else {
        memory_region_init_rom(ram, NULL, name, size, &error_fatal);
    }

    QDICT_ASSERT_KEY_TYPE(mapping, "address", QTYPE_QNUM);
    address = qdict_get_uint(mapping, "address");

    printf("Configurable: Adding memory region %s (size: 0x%"
           PRIx64 ") at address 0x%" PRIx64 "\n", name, size, address);
    memory_region_add_subregion(sysmem, address, ram);

    if (qdict_haskey(mapping, "file"))
    {
        int file;
        const char * filename;
        int dirname_len = get_dirname_len(kernel_filename);
        ssize_t err;
        uint64_t file_offset = 0;

        g_assert(qobject_type(qdict_get(mapping, "file")) == QTYPE_QSTRING);
        filename = qdict_get_str(mapping, "file");

        if (!is_absolute_path(filename))
        {
            char * relative_filename = g_malloc0(dirname_len +
                                                 strlen(filename) + 1);
            g_assert(relative_filename);
            strncpy(relative_filename, kernel_filename, dirname_len);
            strcat(relative_filename, filename);

            file = open(relative_filename, O_RDONLY | O_BINARY);
            data_size = get_file_size(relative_filename);
            g_free(relative_filename);
        }
        else
        {
            file = open(filename, O_RDONLY | O_BINARY);
            data_size = get_file_size(filename);
        }

        if (qdict_haskey(mapping, "file_offset")) {
          off_t sbytes;
          g_assert(qobject_type(qdict_get(mapping, "file_offset")) == QTYPE_QNUM);
          file_offset = qdict_get_uint(mapping, "file_offset");
          sbytes = lseek(file,file_offset,SEEK_SET);
          g_assert(sbytes > 0);
          data_size -= sbytes;

        }

        if (qdict_haskey(mapping,"file_bytes")) {
          ssize_t file_bytes;
          g_assert(qobject_type(qdict_get(mapping, "file_bytes")) == QTYPE_QNUM);
          file_bytes = qdict_get_uint(mapping, "file_bytes");
          data_size = file_bytes;
          printf("File bytes: 0x%lx\n",data_size);

        }

        printf("Configurable: Inserting %"
               PRIx64 " bytes of data in memory region %s\n", data_size, name);
        //Size of data to put into a RAM region needs to fit in the RAM region
        g_assert(data_size <= size);

        data = g_malloc(data_size);
        g_assert(data);

        err = read(file, data, data_size);
        g_assert(err == data_size);

        close(file);

        //And copy the data to the memory, if it is initialized
        printf("Configurable: Copying 0x%" PRIx64
               " byte of data from file %s beginning at offset 0x%" PRIx64
               " to address 0x%" PRIx64
               "\n", data_size, filename, file_offset,address);
        address_space_write_rom(&address_space_memory, address,
                                    MEMTXATTRS_UNSPECIFIED,
                                    (uint8_t *) data, data_size);
        //printf("Config:AddressSpace@:%px\n",&address_space_memory);
        g_free(data);
    }

}

static void init_peripheral(QDict *device)
{
    const char * qemu_name;
    const char * bus;
    const char * name;
    uint64_t address;

    QDICT_ASSERT_KEY_TYPE(device, "address", QTYPE_QNUM);
    QDICT_ASSERT_KEY_TYPE(device, "qemu_name", QTYPE_QSTRING);
    QDICT_ASSERT_KEY_TYPE(device, "bus", QTYPE_QSTRING);
    QDICT_ASSERT_KEY_TYPE(device, "name", QTYPE_QSTRING);

    bus = qdict_get_str(device, "bus");
    qemu_name = qdict_get_str(device, "qemu_name");
    address = qdict_get_int(device, "address");
    name = qdict_get_str(device, "name");

    printf("Configurable: Adding peripheral[%s] region %s at address 0x%" PRIx64 "\n", 
            qemu_name, name, address);
    if (strcmp(bus, "sysbus") == 0)
    {
        SysBusDevice *sb;
        QList *properties = NULL;

        if(qdict_haskey(device, "properties") &&
           qobject_type(qdict_get(device, "properties")) == QTYPE_QLIST)
        {
            properties = qobject_to(QList, qdict_get(device, "properties"));
        }

        sb = make_configurable_device(qemu_name, address, properties);
        qdict_put_obj(peripherals, name, (QObject *)sb);
    }
    else if(strcmp(bus, "fuzzbus") == 0)
    {
        MemoryRegion *sysmem = get_system_memory();
        br_create(sysmem, address);
    }
    else
    {
        g_assert(0); //Right now only sysbus devices are supported ...
    }
}


#define WRITE_WORD(p, value) do { \
    address_space_stl_notdirty(&address_space_memory, p, value, \
                               MEMTXATTRS_UNSPECIFIED, NULL);  \
} while (0)

static void make_writes(QDict* conf, DeviceState* cpudev) {
    WRITE_WORD(0x1337d00d,1234);
    return;

}
#ifdef TARGET_AARCH64
static DeviceState* create_gic_v2(QDict* conf, DeviceState* cpudev) {
    // inspired by the code in virt.c/xlnx-zynqmp.c
    // first, we have to create the GIC
    QListEntry* entry;
    QList* memory_mapping = qobject_to(QList, qdict_get(conf, "memory_mapping"));

    if (memory_mapping == NULL) {
        printf("Configurable: cannot add GIC v2: memory_mapping list not found in config file\n");
        return NULL;
    }

    // right now, there's no need for a custom/redundant GIC config section
    // therefore, we just check the regular memory_mapping list for gic* entries
    // we can always add a custom data structure later if needed
    if (memory_mapping == NULL) {
        printf("Configurable: cannot add GIC v2: gicv2 object not found in config file\n");
        return NULL;
    }

    // prove me wrong in the loop below!
    bool gic_sections_found = false;

    QLIST_FOREACH_ENTRY(memory_mapping, entry) {
        QDict *mmio_mem = qobject_to(QDict, entry->value);
        g_assert(qobject_type(entry->value) == QTYPE_QDICT);
        const char* name = qdict_get_str(mmio_mem, "name");

        if (strncmp(name, "gic", 3) == 0) {
            printf("Configurable: gic* memory mapping \"%s\" found, adding GIC v2\n", name);

            // I wish there was for-else in C/C++
            gic_sections_found = true;
            break;
        }
    }

    if (!gic_sections_found) {
        printf("Configurable: no gic* memory mappings found, not adding GIC v2\n");
        return NULL;
    }

    DeviceState* gic = qdev_new("arm_gic");

    // we have to supply some information before realizing the device
    qdev_prop_set_uint32(gic, "revision", 2);
    // no SMP available in the configurable machine, so this is always 1
    qdev_prop_set_uint32(gic, "num-cpu", 1);

    /* Note that the num-irq property counts both internal and external
     * interrupts; there are always 32 of the former (mandated by GIC spec).
     */
    // TODO: specify some meaningful value
    static const uint32_t NUM_IRQS = 0;
    qdev_prop_set_uint32(gic, "num-irq", NUM_IRQS + 32);

    // not using KVM, so we can set some more properties
    // we do use EL3, as we do TZOS research
    qdev_prop_set_bit(gic, "has-security-extensions", true);
    // however, we do not want EL2 support
    qdev_prop_set_bit(gic, "has-virtualization-extensions", false);

    // so far so good, let's realize the sysbus device
    // not entirely sure yet what that means, but it does sound useful
    SysBusDevice* gicbusdev = SYS_BUS_DEVICE(gic);
    sysbus_realize_and_unref(gicbusdev, &error_fatal);

    /* Wire the outputs from each CPU's generic timer and the GICv3
        * maintenance interrupt signal to the appropriate GIC PPI inputs,
        * and the GIC's IRQ/FIQ/VIRQ/VFIQ interrupt outputs to the CPU's inputs.
        */
    // note: we have just one CPU available, which makes wiring a little easier
    {
        int ppibase = NUM_IRQS + 0 * GIC_INTERNAL + GIC_NR_SGIS;

        // some "defines" from virt.h
        // TODO: allow configuration
        static const int ARCH_TIMER_VIRT_IRQ = 11;
        static const int ARCH_TIMER_S_EL1_IRQ = 13;
        static const int ARCH_TIMER_NS_EL1_IRQ = 14;
        static const int ARCH_TIMER_NS_EL2_IRQ = 10;

        /* Mapping from the output timer irq lines from the CPU to the
         * GIC PPI inputs we use for the virt board.
         */
        const int timer_irq[] = {
            [GTIMER_PHYS] = ARCH_TIMER_NS_EL1_IRQ,
            [GTIMER_VIRT] = ARCH_TIMER_VIRT_IRQ,
            [GTIMER_HYP]  = ARCH_TIMER_NS_EL2_IRQ,
            [GTIMER_SEC]  = ARCH_TIMER_S_EL1_IRQ,
        };

        for (int irq = 0; irq < ARRAY_SIZE(timer_irq); irq++) {
            qdev_connect_gpio_out(
                cpudev,
                irq,
                qdev_get_gpio_in(gic, ppibase + timer_irq[irq])
            );
        }

        // not sure if we need this...
        //         qdev_connect_gpio_out_named(cpudev, "pmu-interrupt", 0,
        //                             qdev_get_gpio_in(gic, ppibase
        //                                                 + VIRTUAL_PMU_IRQ));
        sysbus_connect_irq(gicbusdev, 0, qdev_get_gpio_in(cpudev, ARM_CPU_IRQ));

        sysbus_connect_irq(gicbusdev, 1,
                           qdev_get_gpio_in(cpudev, ARM_CPU_FIQ));
        sysbus_connect_irq(gicbusdev, 2,
                           qdev_get_gpio_in(cpudev, ARM_CPU_VIRQ));
        sysbus_connect_irq(gicbusdev, 3,
                           qdev_get_gpio_in(cpudev, ARM_CPU_VFIQ));
    }

    return gic;
}
#endif


#ifdef TARGET_ARM
static void set_entry_point(QDict *conf, ARMCPU *cpuu)
{
    const char *entry_field = "entry_address";

#ifdef TARGET_AARCH64
    // 64-bit ARM uses a 64-bit entry
    // declaring the variable this way prevents narrowing in the call below
    uint64_t entry;
#else
    uint32_t entry;
#endif


    if(!qdict_haskey(conf, entry_field))
        return;


    QDICT_ASSERT_KEY_TYPE(conf, entry_field, QTYPE_QNUM);
    entry = qdict_get_int(conf, entry_field);
    printf("Configurable: set entry point to %lx\n", (long unsigned int) entry);
    
    // sanity check
    printf(
        "Configurable: cpuu->env.aarch64: %x (should be 0x1 for 64-bit)\n",
        cpuu->env.aarch64
    );

    // bitwise AND to get rid of LSB (used below to switch between modes)
    // set program counter
    // on ARM 32-bit, the PC is in register 15
    // on ARM 64-bit, PC is a special register and is normally not acessible
    // therefore, in CPUARMState in target/arm/cpu.h, pc is modeled as an
    // extra field
#ifdef TARGET_AARCH64
    printf("Configurable: ARM 64-bit -> setting pc register\n");
    cpuu->env.pc = entry & (~1);

    
    

#else
    printf("Configurable: ARM 32-bit -> setting register 15 (pc)\n");
    cpuu->env.regs[15] = entry & (~1);
#endif

#ifndef TARGET_AARCH64
    // avatar2 encodes whether to use thumb mode into the LSB
    // this mode is not available on AArch64 any more, apparently
    cpuu->env.thumb = (entry & 1) == 1 ? 1 : 0;
#endif
}
#elif TARGET_MIPS
static void set_entry_point(QDict *conf, MIPSCPU *cpuu)
{
    //Not implemented yet
}
#endif

#ifdef TARGET_ARM
static ARMCPU *create_cpu(MachineState * ms, QDict *conf)
{
    const char *cpu_model = ms->cpu_type;
    ObjectClass *cpu_oc;
    Object *cpuobj;
    ARMCPU *cpuu;
    CPUState *env;
    DeviceState *dstate; //generic device if CPU can be initiliazed via qdev-API

#ifdef TARGET_AARCH64
    DeviceState *gic;
#endif

    BusState* sysbus = sysbus_get_default();
    int num_irq = 64;

    if (qdict_haskey(conf, "cpu_model"))
    {
        cpu_model = qdict_get_str(conf, "cpu_model");
        g_assert(cpu_model);
    }

    if (!cpu_model) {
#ifdef TARGET_AARCH64
        // this CPU model is used in OP-TEE's QEMU setup, too
        cpu_model = "configurable_a57";
#else
        cpu_model = "arm926";
#endif
    }
    if (getenv("AFL_ENTRY")){
        afl_entry_point = strtoll(getenv("AFL_ENTRY"), NULL, 16);
        printf("set afl_entry_point to "TARGET_FMT_lx"\n", afl_entry_point);
    }
    
    printf("Configurable: Adding processor %s\n", cpu_model);

    //create armv7m cpus together with nvic
    if (!strcmp(cpu_model, "cortex-m3"))
    {

        if (qdict_haskey(conf, "num_irq"))
        {
            num_irq = qdict_get_int(conf, "num_irq");
            g_assert(num_irq);
        }

        dstate = qdev_new("armv7m");
        qdev_prop_set_uint32(dstate, "num-irq", num_irq);
        qdev_prop_set_string(dstate, "cpu-type", ARM_CPU_TYPE_NAME("cortex-m3"));
        object_property_set_link(OBJECT(dstate), "memory", 
            OBJECT(get_system_memory()), &error_abort);
        qdev_realize_and_unref(dstate, sysbus, NULL);

        cpuu = ARM_CPU(first_cpu);

    }
    else
    {
#ifdef TARGET_AARCH64
        // it's important to pass the right type here
        // otherwise, we'll get 32-bit structures
        cpu_oc = cpu_class_by_name(TYPE_AARCH64_CPU, cpu_model);
#else
        cpu_oc = cpu_class_by_name(TYPE_ARM_CPU, cpu_model);
#endif
        if (!cpu_oc) {
            fprintf(stderr, "Unable to find CPU definition\n");
            exit(1);
        }

        cpuobj = object_new(object_class_get_name(cpu_oc));

#ifdef TARGET_AARCH64
        // need to use device abstraction aka qdev to be able to set has_el*
        // don't as me why... let's hope this works
        dstate = DEVICE(cpuobj);

        // OP-TEE doesn't need EL2, and its NW firmware refuses to run in EL2
        // being a TZOS, it needs EL3, though
        qdev_prop_set_bit(dstate, "has_el2", false);
        qdev_prop_set_bit(dstate, "has_el3", true);

        // make sure EL3 is available
        if (object_property_get_bool(cpuobj, "has_el3", NULL)) {
            printf("Configurable: running with EL3\n");
        } else {
            printf("Configurable: EL3 not available\n");
            exit(1);
        }

        // make sure EL2 is _not_ available
        if (object_property_get_bool(cpuobj, "has_el2", NULL)) {
            printf("Configurable: still running with EL2 -- d'oh!\n");
            exit(1);
        } else {
            printf("Configurable: running _without_ EL2 -- yay!\n");
        }
#endif

        object_property_set_bool(cpuobj, "realized", true, &error_fatal);
        cpuu = ARM_CPU(cpuobj);
    }
    env = (CPUState *) &(cpuu->env);
    if (!env)
    {
            fprintf(stderr, "Unable to find CPU definition\n");
            exit(1);
    }

#ifdef TARGET_AARCH64
    // set up global interrupt controller (GIC), if GIC ranges are listed
    // in the memory mappings (called gic*)
    gic = create_gic_v2(conf, dstate);
    
    // TODO: do something useful with that gic
    (void) gic;
#endif

#ifndef TARGET_AARCH64
    // on 64-bit ARM, banked registers don't exist any more
    // therefore, we don't have to execute this step
    avatar_add_banked_registers(cpuu);
#endif

    set_feature(&cpuu->env, ARM_FEATURE_CONFIGURABLE);
    return cpuu;
}


#elif TARGET_MIPS
static MIPSCPU *create_cpu(MachineState * ms, QDict *conf)
{
    const char *cpu_model = ms->cpu_type;
    MIPSCPU *cpuu;
    CPUState *cpu;

    if (qdict_haskey(conf, "cpu_model"))
    {
        cpu_model = qdict_get_str(conf, "cpu_model");
        g_assert(cpu_model);
    }

    if (!cpu_model) cpu_model = "mips32r6-generic";

    printf("Configurable: Adding processor %s\n", cpu_model);

    cpuu = cpu_mips_init(cpu_model);
    if (cpuu == NULL) {
        fprintf(stderr, "Unable to find CPU definition\n");
        exit(1);
    }

    cpu = (CPUState *) &(cpuu->env);
    if (!cpu) {
        fprintf(stderr, "Unable to find CPU definition\n");
        exit(1);
    }

    return cpuu;
}
#endif


static void board_init(MachineState * ms)
{
#ifdef TARGET_ARM
    ARMCPU *cpuu;
#elif TARGET_MIPS
    MIPSCPU *cpuu;
#endif

    const char *kernel_filename = ms->kernel_filename;
    QDict * conf = NULL;

    //Load configuration file
    if (kernel_filename)
    {
        conf = load_configuration(kernel_filename);
    }
    else
    {
        conf = qdict_new();
    }

    cpuu = create_cpu(ms, conf);
    set_entry_point(conf, cpuu);

    if (qdict_haskey(conf, "memory_mapping"))
    {
        peripherals = qdict_new();
        QListEntry * entry;
        QList * memories = qobject_to(QList, qdict_get(conf, "memory_mapping"));
        g_assert(memories);

        QLIST_FOREACH_ENTRY(memories, entry)
        {
            g_assert(qobject_type(entry->value) == QTYPE_QDICT);
            QDict *mapping = qobject_to(QDict, entry->value);

            if((qdict_haskey(mapping, "qemu_name") &&
                qobject_type(qdict_get(mapping, "qemu_name")) == QTYPE_QSTRING))
            {
                init_peripheral(mapping);
                continue;
            } else {
                init_memory_area(mapping, kernel_filename);
            }

        }
    //hack for setting tick-value
    WRITE_WORD(0xfff08020,0x3b9aca0);

    }
}

static void configurable_machine_class_init(ObjectClass *oc, void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);

    mc->desc = "Machine that can be configured to be whatever you want";
    mc->init = board_init;
    mc->block_default_type = IF_SCSI;
}

static const TypeInfo configurable_machine_type = {
    .name       =  MACHINE_TYPE_NAME("configurable"),
    .parent     = TYPE_MACHINE,
    .class_init = configurable_machine_class_init,
};

static void configurable_machine_init(void)
{
    type_register_static(&configurable_machine_type);
}

type_init(configurable_machine_init);
