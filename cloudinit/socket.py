# This file is part of cloud-init. See LICENSE file for license information.
"""A module for common socket helpers."""
import logging
import os
import socket
from contextlib import suppress

from cloudinit.settings import DEFAULT_RUN_DIR

LOG = logging.getLogger(__name__)


def sd_notify(message: bytes):
    """Send a sd_notify message."""
    LOG.info("Sending sd_notify(%s)", str(message))
    socket_path = os.environ.get("NOTIFY_SOCKET", "")

    # abstract
    if socket_path[0] == "@":
        socket_path.replace("@", "\0", 1)

    # unix domain
    elif not socket_path[0] == "/":
        raise OSError("Unsupported socket type")

    with socket.socket(
        socket.AF_UNIX, socket.SOCK_DGRAM | socket.SOCK_CLOEXEC
    ) as sock:
        sock.connect(socket_path)
        sock.sendall(message)


class SocketSync:
    """A two way synchronization protocol over Unix domain sockets."""

    def __init__(self, *names: str):
        """Initialize a synchronization context.

        1) Ensure that the socket directory exists.
        2) Bind a socket for each stage.

        Binding the sockets on initialization allows receipt of stage
        "start" notifications prior to the cloud-init stage being ready to
        start.

        :param names: stage names, used as a unique identifiers
        """
        self.stage = ""
        self.remote = ""
        self.sockets = {
            name: socket.socket(
                socket.AF_UNIX, socket.SOCK_DGRAM | socket.SOCK_CLOEXEC
            )
            for name in names
        }
        # ensure the directory exists
        os.makedirs(f"{DEFAULT_RUN_DIR}/share", mode=0o700, exist_ok=True)
        # removing stale sockets and bind
        for name, sock in self.sockets.items():
            socket_path = f"{DEFAULT_RUN_DIR}/share/{name}.sock"
            with suppress(FileNotFoundError):
                os.remove(socket_path)
            sock.bind(socket_path)

    def __call__(self, stage: str):
        """Set the stage before entering context.

        This enables the context manager to be initialized separately from
        each stage synchronization.

        :param stage: the name of a stage to synchronize

        Example:
            sync = SocketSync("stage 1", "stage 2"):
            with sync("stage 1"):
                pass
            with sync("stage 2"):
                pass
        """
        self.stage = stage
        return self

    def __enter__(self):
        """Wait until a message has been received on this stage's socket.

        Once the message has been received, enter the context.
        """
        LOG.debug("sync(%s): initial synchronization starting", self.stage)
        # block until init system sends us data
        # the first value returned contains a message from the init system
        #     (should be "start")
        # the second value contains the path to a unix socket on which to
        #     reply, which is expected to be /path/to/{self.stage}-return.sock
        sock = self.sockets[self.stage]
        chunk, self.remote = sock.recvfrom(5)

        if b"start" != chunk:
            # The protocol expects to receive a command "start"
            self.__exit__(None, None, None)
            raise ValueError(f"Received invalid message: [{str(chunk)}]")
        elif f"{DEFAULT_RUN_DIR}/share/{self.stage}-return.sock" != str(
            self.remote
        ):
            # assert that the return path is in a directory with appropriate
            # permissions
            self.__exit__(None, None, None)
            raise ValueError(f"Unexpected path to unix socket: {self.remote}")

        LOG.debug("sync(%s): initial synchronization complete", self.stage)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Notify the socket that this stage is complete."""
        sock = self.sockets[self.stage]
        sock.connect(self.remote)
        sock.sendall(b"done")
        sock.close()
