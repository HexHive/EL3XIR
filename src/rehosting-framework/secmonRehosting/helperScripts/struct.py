import io

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
