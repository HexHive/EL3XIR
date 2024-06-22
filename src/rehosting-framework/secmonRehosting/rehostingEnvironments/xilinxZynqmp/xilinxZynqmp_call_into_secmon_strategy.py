from ..call_into_secmon_strategy import CallIntoSecMonStrategy
from ...helperScripts.struct import Struct


class XilinxZynqmpCallIntoSecMonStrategyBase(CallIntoSecMonStrategy):
    def __init__(self, *args, **kwargs):
        pass

    def parse_return_value(self) -> "Struct":

        pass

    def execute_secmon_command(self):
        pass

