# This file is part of cloud-init. See LICENSE file for license information.
"""A module for common socket helpers."""
import logging
import os
import socket
import sys
import time
from contextlib import suppress

from cloudinit.settings import DEFAULT_RUN_DIR

LOG = logging.getLogger(__name__)


def sd_notify(message: str):
    """Send a sd_notify message.

    :param message: sd-notify message (must be valid ascii)
    """
    socket_path = os.environ.get("NOTIFY_SOCKET", "")

    if not socket_path:
        # not running under systemd, no-op
        return

    elif socket_path[0] == "@":
        # abstract
        socket_path.replace("@", "\0", 1)

    # unix domain
    elif socket_path[0] != "/":
        raise OSError("Unsupported socket type")

    with socket.socket(
        socket.AF_UNIX, socket.SOCK_DGRAM | socket.SOCK_CLOEXEC
    ) as sock:
        LOG.info("Sending sd_notify(%s)", str(message))
        sock.connect(socket_path)
        sock.sendall(message.encode("ascii"))


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
        self.first_exception = ""
        self.systemd_exit_code = 0
        self.experienced_any_error = False
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
        if stage not in self.sockets:
            raise ValueError(f"Invalid stage name: {stage}")
        self.stage = stage
        return self

    def __enter__(self):
        """Wait until a message has been received on this stage's socket.

        Once the message has been received, enter the context.
        """
        if os.isatty(sys.stdin.fileno()):
            LOG.info(
                "Stdin is a tty, so skipping stage synchronization protocol"
            )
            return
        self.systemd_exit_code = 0
        sd_notify(
            "STATUS=Waiting on external services to "
            f"complete before starting the {self.stage} stage."
        )
        start_time = time.monotonic()
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

        total = time.monotonic() - start_time
        time_msg = f"took {total: .3f}s to " if total > 0.01 else ""
        sd_notify(f"STATUS=Running ({self.stage} stage)")
        LOG.debug("sync(%s): synchronization %scomplete", self.stage, time_msg)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Notify the socket that this stage is complete."""
        message = f"Completed socket interaction for boot stage {self.stage}"
        if exc_type:
            # handle exception thrown in context
            self.systemd_exit_code = 1
            self.experienced_any_error = True
            status = f"{repr(exc_val)} in {exc_tb.tb_frame}"
            message = (
                'fatal error, run "systemctl status cloud-init-main.service" '
                'and "cloud-init status --long" for more details'
            )
            if not self.first_exception:
                self.first_exception = status
            LOG.fatal(status)
            sd_notify(f"STATUS={status}")

        self.experienced_any_error = self.experienced_any_error or bool(
            self.systemd_exit_code
        )
        sock = self.sockets[self.stage]
        sock.connect(self.remote)

        # the returned message will be executed in a subshell
        # hardcode this message rather than sending a more informative message
        # to avoid having to sanitize inputs (to prevent escaping the shell)
        sock.sendall(
            f"echo '{message}'; exit {self.systemd_exit_code};".encode()
        )
        sock.close()

        # suppress exception - the exception was logged and the init system
        # notified of stage completion (and the exception received as a status
        # message). Raising an exception would block the rest of boot, so carry
        # on in a degraded state.
        return True
