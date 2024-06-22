#! /usr/bin/env python3

"""
Simple socket server that prints all incoming messages to the console.
Alternative to netcat that survives disconnects and supports listening on multiple ports.
Note that this little program requires Python 3.6+.
"""

import asyncio
import itertools
import sys
from typing import List

import click


def log(message: str):
    print(message, file=sys.stderr)


def sanitize(text: str):
    # note: ranges exclude the last character
    valid_range = list(
        itertools.chain(
            range(0x9, 0xE),
            range(0x20, 0x127),
        )
    )

    out = []
    for char in text:
        byte = ord(char)
        if byte not in valid_range:
            out.append("\\{}".format(hex(byte).lstrip("0")))
        else:
            out.append(char)

    return "".join(out)


class PrefixedLinePrinter:
    """
    Prints all lines in data blobs with a prefix.
    Buffers remaining data until a line feed is detected.
    Note: there is currently no easy way to print data remaining the buffer upon program termination.
    """

    def __init__(self, prefix: str):
        self.prefix = prefix
        self.buffer = []

    def add_data(self, data: str):
        self.buffer += list(data)

    def print_buffered_lines(self):
        while True:
            # search for the end of the next line
            try:
                # note: we cannot simply use str.splitlines, since it makes too many assumptions on what a line is
                # we assume a line is a (sub)string that is terminated by a \n character
                next_lf = self.buffer.index("\n")

            except ValueError:
                break

            # print next line with prefix, including original termination
            print(f"{self.prefix}{''.join(self.buffer[:next_lf + 1])}", end="")

            # remove current line from buffer
            self.buffer = self.buffer[next_lf + 1 :]


class PrintServerProtocol(asyncio.Protocol):
    def __init__(self):
        super().__init__()

        # will be initialized in connection_made
        self.transport = None
        self.printer = None

    def connection_made(self, transport):
        _, listen_port = transport.get_extra_info("sockname")[:2]
        self.line_prefix = "[{}] ".format(listen_port)

        host, port = transport.get_extra_info("peername")[:2]
        log("{}Client connected: {}:{}".format(self.line_prefix, host, port))

        self.transport = transport

        self.printer = PrefixedLinePrinter(self.line_prefix)

    def data_received(self, data):
        text = data.decode()

        # replace all "special" characters with a "fake" escape sequence
        text = sanitize(text)

        # if \r stands for itself, we replace it with \n to make sure we don't lose output
        # text = re.sub(r"([^\n])\r([^\n])", r"\1\\r\n\2", text, re.MULTILINE)

        self.printer.add_data(text)
        self.printer.print_buffered_lines()

        sys.stdout.flush()

    def connection_lost(self, exc):
        host, port = self.transport.get_extra_info("peername")[:2]
        log(f"{self.line_prefix}Client disconnected: {host}:{port}")


async def serve_on_ports(ports: List[int] = None):
    loop = asyncio.get_event_loop()

    for port in ports:
        # for some annoying reason, listening on both IPv4 and IPv6 is overly complicated
        for host in ["::1", "127.0.0.1"]:
            log(f"Starting server: {host}:{port}")
            try:
                await loop.create_server(lambda: PrintServerProtocol(), host, port)
            except OSError as e:
                log(f"error: {e}")


@click.command()
@click.argument("ports", nargs=-1, type=int, required=True)
def main(ports):
    """
    Simple socket server that prints all incoming messages to the console.

    Very useful for use with QEMU's -serial flag (e.g., "-serial tcp:localhost:<port>"). QEMU will connect to the
    server.
    The script survives restarts of QEMU, so you can just let it run in a terminal window while tinkering with QEMU.
    """

    loop = asyncio.get_event_loop()

    log("Serving forever...")
    loop.run_until_complete(serve_on_ports(ports))

    try:
        loop.run_forever()

    except KeyboardInterrupt:
        log("\nSIGINT received, shutting down")

        loop.close()
        loop.stop()


if __name__ == "__main__":
    main()
