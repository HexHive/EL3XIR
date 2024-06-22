import io
from typing import Union

from avatar2.peripherals import AvatarPeripheral

from .. import get_logger


class InMemoryBufferPeripheral(AvatarPeripheral):
    """
    An Avatar2 peripheral holding an in-memory buffer, forwarding reads and writes to that.
    It's writable/readable directly without the need of using some target's write_memory, which is not only a lot
    faster and easier to use, but also allows for writing data before the targets are initialized.
    """

    logger = get_logger("in_memory_buffer")

    def __init__(self, name, address, size, **kwargs):
        super().__init__(name, address, size, **kwargs)

        # this holds all the data that read/write will return
        self.buffer = io.BytesIO()

    @staticmethod
    def _check_preconditions(size: int, num_words: int, raw: bool):
        # so far we haven't had to support more than one word at a time
        # if this should ever change, we can add support for that
        assert num_words == 1

        # in raw mode, reading returns and writing takes bytes instead of ints
        # in non-raw mode, we have to convert the bytes into an int with the correct endianness
        if not raw:
            # the actual limit would likely be 8, which is the size of a 64-bit int
            # however, at this point, we haven't had to support more than 4 bytes, as the remote memory reads only ever
            # request 4 bytes at a time
            # therefore, we'll keep it limited to 4 until our requirements change
            assert size <= 4

    def read_memory(self, address: int, size: int, num_words: int = 1, raw: bool = False) -> Union[bytes, int]:
        """
        Read memory from the buffer. Inherited from AvatarPeripheral.
        """

        self._check_preconditions(size, num_words, raw)

        # avatar2 passes absolute addresses; we must read our buffer at the correct offset, though
        offset = address - self.address

        # buffer works like a file, so we can use seek/read to get data out of it
        self.buffer.seek(offset, io.SEEK_SET)
        data = self.buffer.read(size)

        # pad with/append null bytes if needed
        padded_data = data.ljust(size, b"\x00")

        def log_debug_message(printed_data: str):
            self.logger.debug(f'read "{self.name}" address={hex(address)} offset={hex(offset)} data={printed_data}')

        # as mentioned before, we have to convert the data into a little-endian int
        if raw:
            log_debug_message("hidden in raw mode")
            return padded_data

        else:
            rv = int.from_bytes(padded_data, "little")
            log_debug_message(hex(rv))
            return rv

    def write_memory(self, address: int, size: int, value: Union[bytes, int], num_words: int = 1, raw: bool = False):
        """
        Write memory to the buffer. Inherited from AvatarPeripheral.
        """

        self._check_preconditions(size, num_words, raw)

        # avatar2 passes absolute addresses; we must read our buffer at the correct offset, though
        offset = address - self.address

        def log_debug_message(printed_data: str):
            self.logger.debug(f'write "{self.name}" address={hex(address)} offset={hex(offset)} data={printed_data}')

        if raw:
            # in raw mode, we will be handed bytes directly
            log_debug_message("hidden in raw mode")
            data = value

        else:
            # in non-raw mode, value will be an int, which means we first have to convert it to bytes first
            log_debug_message(hex(value))
            data = value.to_bytes(size, "little")

        # buffer works like a file, so we can use seek/write to modify it
        self.buffer.seek(offset, io.SEEK_SET)
        self.buffer.write(data)

        # flushing the buffer to make sure written data is visible upon future operations
        self.buffer.flush()

        # apparently, we have to signal whether writes have succeeded
        return True

    def write_into_buffer(self, data: bytes):
        """
        Convenience method, used to write data directly into the buffer at its beginning.

        Might be extended later on with additional functionality such as configurable offsets.
        """

        # now that write_memory supports the raw flag, we can make this a shallow wrapper to avoid code duplication
        self.write_memory(self.address, len(data), data, raw=True)
