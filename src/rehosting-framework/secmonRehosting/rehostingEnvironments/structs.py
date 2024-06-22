import io
import struct
from typing import NamedTuple
from typing import List
from avatar2 import Target

class Struct:
    @classmethod
    def from_memory(cls, target: Target, start_address: int):
        """
        Read struct from memory, using Avatar2's remote memory interface.

        The advantage of implementing this instead of, e.g., a from_bytes method, is that the caller does not need to
        know the amount of bytes that will be consumed. This allows for implementing reading recursively, with
        dynamically sized elements like arrays of child structs whose size is defined by another member.

        :param target: target to use for reading memory
        :param start_address: address to start reading at
        """

        raise NotImplementedError()

    def serialize(self, buffer: io.BytesIO):
        """
        Serialize all attributes recursively into the provided buffer object.
        """

        raise NotImplementedError()

    def to_bytes(self) -> bytes:
        """
        Serialize all attributes recursively into a buffer, and return its contents as bytes.
        """

        buffer = io.BytesIO()
        self.serialize(buffer)

        buffer.seek(0, io.SEEK_SET)

        return buffer.read()

class StaticSizeStruct(Struct):
    @classmethod
    def calcsize(cls):
        return struct.calcsize(cls.fmt)

class BlParam(NamedTuple):
    addr: int
    structure: StaticSizeStruct

"""
typedef struct bl_params_node {
	unsigned int image_id;
	image_info_t *image_info;
	entry_point_info_t *ep_info;
	struct bl_params_node *next_params_info;
} bl_params_node_t;
"""

class Bl31Params(StaticSizeStruct):
    # BL31_params basically tells bl31 where to find info about the the other boot_roms,
    # This firmware is just interested in *_ep_info, which tells the firmware how to jump
    # into the bl!
    # struct bl31_params
    # {
    # param_header_t h;
    # image_info_t * bl31_image_info;
    # entry_point_info_t * bl32_ep_info;
    # image_info_t * bl32_image_info;
    # entry_point_info_t * bl33_ep_info;
    # image_info_t * bl33_image_info;
    # };
    # from ghidra it seems at least, that the uint32's are padded to uint64's -> q as FMT
    fmt = "<" + 5 * "Q"

    def __init__(
            self,
            bl31_image_info: int,
            bl32_ep_info: int,
            bl32_image_info: int,
            bl33_ep_info: int,
            bl33_image_info: int,
    ):
        self.h = _ParamHeader(0x03, 0x1, 0x30, 0)
        self.bl31_image_info = bl31_image_info
        self.bl32_ep_info = bl32_ep_info
        self.bl32_image_info = bl32_image_info
        self.bl33_ep_info = bl33_ep_info
        self.bl33_image_info = bl33_image_info

    # @classmethod
    # def from_memory(cls, target: Target, start_address: int):
    #     # most likely not needed, as we don't have any bootloader structure to read or the bl31 would take of itself.
    #     struct_fmt = "<" + 8 * "I"
    #     struct_size = struct.calcsize(struct_fmt)
    #
    #     bl31_param_data = target.read_memory(start_address, struct_size, raw=True)
    #     h, bl31_image_info, bl32_ep_info, bl33_ep_info, bl33_image_info = struct.unpack(struct_fmt, bl31_param_data)
    #
    #     return cls(h, bl31_image_info, bl32_ep_info, bl33_ep_info, bl33_image_info)

    def serialize(self, buffer: io.BytesIO):
        data = self.h.serialize()
        data = data + struct.pack(
            self.fmt,
            self.bl31_image_info,
            self.bl32_ep_info,
            self.bl32_image_info,
            self.bl33_ep_info,
            self.bl33_image_info,
        )
        buffer.write(data)

    @classmethod
    def calcsize(cls):
        return _ParamHeader.calcsize() + struct.calcsize(cls.fmt)


class EntryPointInfo(StaticSizeStruct):
    # pc = entrypoint of BL
    # spsr = spsrs register... -> https://www.keil.com/support/man/docs/armasm/armasm_dom1359731139484.htm
    # struct entry_point_info
    # {
    # param_header_t h;
    # uintptr_t pc;
    # uint32_t spsr;
    # char[4] pad;
    # aapcs64_params_t
    # args;
    # };
    fmt = "<" + 4 * "I"

    def __init__(
            self,
            pc: int,
            spsr: int,
            args: [],
            secure: int
    ):
        self.h = _ParamHeader(0x01, 0x1, 0x58, secure)
        self.pc = pc
        self.spsr = spsr
        self.args = Aapcs64Params(args)

    # @classmethod
    # def from_memory(cls, target: Target, start_address: int):
    #     # if we would have a running bl2, we would not have to pull this stunt...
    #     raise NotImplementedError()

    def serialize(self, buffer: io.BytesIO):
        # aapcs64_params_t is exactly 8 ulongs long! At least Ghidra is of the opinion that this is 64 Bytes.

        data = self.h.serialize()
        data = data + struct.pack(
            self.fmt,
            self.pc,
            0,
            self.spsr,
            0,
        )
        data = data + self.args.serialize()
        buffer.write(data)

    @classmethod
    def calcsize(cls):
        return _ParamHeader.calcsize() + struct.calcsize(cls.fmt) + Aapcs64Params.calcsize()


class ImageInfo(StaticSizeStruct):
    # struct image_info
    # {
    # param_header_t h;
    # uintptr_t image_base;
    # uint32_t image_size;
    # char[4] pad;
    # };
    fmt = "<QQ"

    def __init__(
            self,
            image_base: int,
            image_size: int,
            secure: int
    ):
        self.h = _ParamHeader(0x02, 0x1, 0x18, secure)
        self.image_base = image_base
        self.image_size = image_size

    # @classmethod
    # def from_memory(cls, target: Target, start_address: int):
    #     # if we would have a running bl2, we would not pull this stunt...
    #     raise NotImplementedError()

    def serialize(self, buffer: io.BytesIO):
        # Compiler pads for alignment why we are using Q as FMT
        data = self.h.serialize()
        data = data + struct.pack(self.fmt, self.image_base, self.image_size)
        buffer.write(data)

    @classmethod
    def calcsize(cls):
        return _ParamHeader.calcsize() + struct.calcsize(cls.fmt)


class _ParamHeader(StaticSizeStruct):
    # INTERNAL class, you never should need to instantiate your own param_header!
    # struct param_header
    # {
    # uint8_t type;
    # uint8_t version;
    # uint16_t size;
    # uint32_t attr;
    # };
    fmt = "<BBHI"

    def __init__(
            self,
            type: int,
            version: int,
            size: int,
            attr: int,
    ):
        self.type = type
        self.version = version
        self.size = size
        self.attr = attr

    # @classmethod
    # def from_memory(cls, target: Target, start_address: int):
    #     # if we would have a running bl2, we would not pull this stunt...
    #     raise NotImplementedError()

    def serialize(self) -> bytes:
        data = struct.pack(self.fmt, self.type, self.version, self.size, self.attr)
        return data


class Aapcs64Params(StaticSizeStruct):
    fmt = "<" + 8 * "Q"

    def __init__(
            self,
            args: [],
    ):

        if len(args) > 8:
            raise Exception("only 8 args are allowed!")
        else:  # padding with 0! till we have a list of 8 args
            self.args = args
            for _ in range(len(self.args), 8):
                self.args.append(0)

    # def from_memory(cls, target: Target, start_address: int):
    #     # if we would have a running bl2, we would not pull this stunt...
    #     raise NotImplementedError()

    def serialize(self) -> bytes:
        data = struct.pack(
            self.fmt,
            self.args[0],
            self.args[1],
            self.args[2],
            self.args[3],
            self.args[4],
            self.args[5],
            self.args[6],
            self.args[7],
        )
        return data