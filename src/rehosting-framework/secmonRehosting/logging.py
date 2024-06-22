import logging
import os

import coloredlogs


def get_logger(name: str = None):
    """
    Logger singleton factory function.

    :param name: if provided, a child logger of the parent logger with the given name will be created
        otherwise, the top-level logger will be returned
    :returns: top-level logger or, if name given, child logger
    """

    default_logger = logging.getLogger("rehostee")

    # in Python, loggers have a parent-child relationship. logger A.B would be a child of A, for instance
    # child loggers inherit parents' configuration, like, e.g., the log levels
    if name:
        # this is nothing but a shortcut, calling getChild outside the method works just as well
        return default_logger.getChild(name)

    return default_logger


def install_logging():
    """
    Set up logging in the console properly using coloredlogs.
    """

    # better log format: less verbose, but including milliseconds
    fmt = "%(asctime)s,%(msecs)03d %(name)s [%(levelname)s] %(message)s"

    # the handler installed by coloredlogs shall be configured to show all messages, including debug ones
    # this way, we can configure the loggers' levels individually, and, for example, show debug messages for selected
    # ones, whereas by default only info and above will be shown
    coloredlogs.install(logging.DEBUG, fmt=fmt)

    # to make quick-and-dirty debugging easy, we support a $DEBUG environment variable
    # if set to any value, we enable debug logging on the parent logger and thus all child loggers as well
    default_loglevel = logging.INFO

    if "DEBUG" in os.environ:
        default_loglevel = logging.DEBUG

    get_logger().setLevel(default_loglevel)

    # reduce the amount of spam coming from avatar2 and its dependencies
    # we do this selectively for the loggers we know are annoying
    # this way, custom loggers (or ones we don't know yet) are not hidden
    # consider this an excludelist
    if "DEBUG_AVATAR" not in os.environ:
        for logger_name in ["avatar", "pygdbmi"]:
            logging.getLogger(logger_name).setLevel(logging.WARNING)

    # allow user to enable debug output for any logger via an environment variable containing a ;-separated list
    debug_loggers = os.environ.get("DEBUG_LOGGERS", "")

    if ";" in debug_loggers:
        debug_loggers = debug_loggers.split(";")
    else:
        debug_loggers = [debug_loggers]

    for logger_name in debug_loggers:
        logging.getLogger(logger_name).setLevel(logging.DEBUG)
