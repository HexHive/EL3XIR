from typing import TYPE_CHECKING, Optional

from avatar2 import Target, MemoryRange

from ..helperScripts.colored_register_printer import ColoredRegistersPrinter
from ..helperScripts.target_bridge import TargetBridge

if TYPE_CHECKING:
    from ..helperScripts import ConvenientAvatar


class RehostingContext:
    """
    Common state shared between multiple components.
    Further implements some convenience functionality needed by some of the components.
    """

    def __init__(
        self,
        avatar: "ConvenientAvatar",
        target: Target,
        target_bridge: TargetBridge,
        colored_register_printer: Optional[ColoredRegistersPrinter] = None,
    ):
        self.avatar = avatar
        self.target = target

        self.target_bridge: TargetBridge = target_bridge

        self.colored_register_printer = colored_register_printer
