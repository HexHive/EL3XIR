from .breakpoint_handling_runner import BreakpointToHandlerMap


class BreakpointHandler:
    """
    Basic interface for breakpoint handlers.
    """

    def handled_breakpoints(self) -> BreakpointToHandlerMap:
        raise NotImplementedError()


class BreakpointHandlerBase(BreakpointHandler):
    """
    Abstract base class that implements functionality common to all breakpoint handlers.
    """

    def __init__(self):
        self._handled_breakpoints: BreakpointToHandlerMap = {}

    def _register_handler_for_breakpoint(self, bp_address: int, callback: callable):
        if bp_address in self._handled_breakpoints:
            raise ValueError(f"handler already registered for address {hex(bp_address)}: callback")

        self._handled_breakpoints[bp_address] = callback

    def handled_breakpoints(self) -> BreakpointToHandlerMap:
        return self._handled_breakpoints
