import typing

if typing.TYPE_CHECKING:
    from .rehosting_context import RehostingContext
    from ..helperScripts.struct import Struct


class CallIntoSecMonStrategy:
    """
    Interface for strategies that implement calls into the TZOS

    Implementation of the strategy pattern.
    """

    def execute_secmon_command(self) -> "Struct":
        raise NotImplementedError()

    def parse_return_value(self) -> "Struct":
        raise NotImplementedError()


