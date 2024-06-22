import itertools
import typing

from colorama import Fore, Style

if typing.TYPE_CHECKING:
    from .target_bridge import TargetBridge


class ColoredRegistersPrinter:
    """
    Little utility that fetches register values from an Avatar2 target and prints them colorfully.
    Formats changed register values bold.
    """

    _colors = [
        Fore.RESET,
        Fore.RED,
        Fore.GREEN,
        Fore.YELLOW,
        Fore.BLUE,
        Fore.MAGENTA,
        Fore.CYAN,
        Fore.WHITE,
        Fore.LIGHTRED_EX,
        Fore.LIGHTGREEN_EX,
        Fore.LIGHTYELLOW_EX,
        Fore.LIGHTBLUE_EX,
        Fore.LIGHTMAGENTA_EX,
        Fore.LIGHTCYAN_EX,
    ]

    def __init__(self, target_bridge: "TargetBridge"):
        self._target_bridge = target_bridge

        # could be made configurable in the future
        # should be an ordered container to maintain the order later when printing them
        self._registers = ["pc"]

        for i in range(13):
            self._registers.append(f"r{i}")

        # seed cache with None values
        self._cached_register_values = {name: None for name in self._registers}

    @staticmethod
    def _print_register(color: str, name: str, value: int, bold: bool = False):
        message = f"{color}{name}={hex(value)[2:].ljust(8)}"

        if bold:
            message = Style.BRIGHT + message

        message += Style.RESET_ALL

        print(message, end="  ")

    def _read_registers(self):
        return {name: self._target_bridge.read_register(name) for name in self._registers}

    def print_registers(self):
        new_values = self._read_registers()

        for color, name in zip(itertools.cycle(self._colors), self._registers):
            old_value = self._cached_register_values[name]
            new_value = new_values[name]
            self._print_register(color, name, new_value, (old_value != new_value))
            self._cached_register_values[name] = new_value

        print(Fore.RESET)
