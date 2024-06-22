from .call_into_secmon_strategy import CallIntoSecMonStrategy
from ..helperScripts import BreakpointHandlingRunner
from ..helperScripts.struct import Struct


class NonSecMonBreakpointHit(Exception):
    pass


class SecMonBooted(Exception):
    pass


class SecMonCommandFinished(Exception):
    pass


class SecMonCommandFailed(Exception):

    def __init__(self, struct: Struct):
        super().__init__()
        self.struct = struct

    def __repr__(self):
        return f"<{self.__class__.__name__} struct={self.struct}>"


class SecMonRunner:
    """
    Adapter for BreakpointHandlingRunner to provide the previously available workflow to the script. Handles exceptions
    raised by secure monitor breakpoint handler.
    """

    def __init__(self, runner: BreakpointHandlingRunner, call_into_secmon_strategy: CallIntoSecMonStrategy):
        self._call_into_tzos_strategy = call_into_secmon_strategy
        self._runner = runner

    def cont(self):
        """
        Continue execution until one of the following events occurs:

        - SecMon booted (returns to Normal World Boot)
        - SMC command finished (returns parsed result)
        """

        try:
            self._runner.cont()

        except SecMonCommandFinished:
            return
            # return self._call_into_secmon_strategy.parse_return_value()

        except SecMonBooted:
            return

        # raising an exception is an easy-to-understand and -implement way to pass back control to the caller
        raise NonSecMonBreakpointHit()

    def execute_secmon_command(self, msg_arg: Struct, fail_silently: bool = False):
        return
