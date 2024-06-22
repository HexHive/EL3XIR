from typing import Dict, Set, TYPE_CHECKING

from avatar2 import Target, TargetStates

if TYPE_CHECKING:
    from . import BreakpointHandler

from .. import get_logger


BreakpointToHandlerMap = Dict[int, callable]


class BreakpointHandlingRunner:
    """
    Wraps an Avatar2 target. Allows breakpoint handlers to register themselves. When the execution is continued, known
    breakpoints are dispatched to the respective handlers, and handled internally. Unknown breakpoints (e.g., ones set
    by the user outside the runner) pass control back to the caller.

    Combination of the facade and observer patterns.
    """

    def __init__(self, target: Target):
        self._target = target

        self._breakpoint_handlers: Set["BreakpointHandler"] = set()

        self._logger = get_logger("bp_handling_runner")

    def _check_class_invariants(self):
        # this method asserts that every breakpoint is registered by only one handler
        self._make_breakpoints_map()

    def _make_breakpoints_map(self) -> BreakpointToHandlerMap:
        map: BreakpointToHandlerMap = {}

        for handler in self._breakpoint_handlers:
            handled_breakpoints = handler.handled_breakpoints()

            for bp_address, bp_handler in handled_breakpoints.items():
                if bp_address in map:
                    raise ValueError(f"handler already registered for address {bp_address}: {map[bp_address]}")

                map[bp_address] = bp_handler

        return map

    def cont(self):
        """
        Continue execution, handling known breakpoints internally until an unknown one is hit. In this case, the method
        returns.

        The function installs the breakpoints the runner handles internally right before it continues execution, and
        makes sure they are removed again before returning.

        Note: Avatar2 does not allow us to check whether a breakpoint is set already. Therefore, if user-set
        breakpoints happen to be registered by a handler as well, they will be removed by this method. We cannot warn
        users about this, unfortunately. In the future, a decorator for QEMU targets might be introduced that keeps
        track of breakpoints.
        """

        self._check_class_invariants()

        bps_map = self._make_breakpoints_map()

        try:
            for bp_address in bps_map.keys():
                self._target.set_breakpoint(bp_address)

            # this loop provides the magic: it retains the synchronous interface expected from Avatar2 targets' cont()
            # we just continue, wait for a breakpoint, check if we know it, and decide what to do:
            # if we know the breakpoint's address, we call the handler, wait for it to return, and continue
            # if not, we return
            while True:
                # continue until breakpoint is hit
                self._target.cont()
                self._target.wait()

                bp_address = self._target.read_register("pc")

                try:
                    callback = bps_map[bp_address]

                except KeyError:
                    return

                callback()

        finally:
            # as promised, we remove all breakpoints we added beforehand (but only if the target isn't exited)
            if self._target.state != TargetStates.EXITED:
                for bp_address in bps_map.keys():
                    self._target.remove_breakpoint(bp_address)

            self._check_class_invariants()

    def register_handler(self, bp_handler: "BreakpointHandler"):
        """
        Register new breakpoint handler.

        Only one handler may be registered for one breakpoint address. An exception is thrown in this case.

        :param bp_handler: handler to register
        :raises ValueError: if new breakpoint handler wants to handle breakpoint another handler is subscribed to
        """

        self._check_class_invariants()

        # the requirement to have handlers handle unique breakpoints is modeled as a precondition
        # of course it's a bit unfair, as the caller can't know whether a breakpoint is registered already
        # thus, they might not necessarily be responsible for the violation
        # however, we can't work around this limitation internally, so we let the caller deal with it
        # typically, there is no reason to register multiple handlers that want to register the same breakpoints, so
        # it's likely a programming error
        handlers_to_register = bp_handler.handled_breakpoints()

        bps_map = self._make_breakpoints_map()

        for bp_address in handlers_to_register.keys():
            if bp_address in bps_map:
                raise ValueError(f"breakpoint {hex(bp_address)} already registered to handler {bps_map[bp_address]}")

        # everything seems good, so let's add the handler
        self._breakpoint_handlers.add(bp_handler)

        self._check_class_invariants()
