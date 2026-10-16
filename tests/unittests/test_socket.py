import socket
import sys
import uuid
from unittest import mock

import pytest

from cloudinit import socket as ci_socket


@pytest.fixture
def notify_receiver():
    """A datagram socket standing in for the init system's notify socket"""
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.settimeout(1)
        yield sock


class TestSdNotify:
    def test_no_notify_socket_is_noop(self, monkeypatch):
        """Nothing is sent when not running under systemd"""
        monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
        with mock.patch.object(ci_socket.socket, "socket") as m_socket:
            ci_socket.sd_notify("READY=1")
        assert 0 == m_socket.call_count

    def test_path_socket(self, monkeypatch, notify_receiver, tmp_path):
        """A NOTIFY_SOCKET starting with '/' is a filesystem path"""
        path = str(tmp_path / "notify")
        notify_receiver.bind(path)
        monkeypatch.setenv("NOTIFY_SOCKET", path)
        ci_socket.sd_notify("READY=1")
        assert b"READY=1" == notify_receiver.recv(4096)

    @pytest.mark.skipif(
        not sys.platform.startswith("linux"),
        reason="abstract sockets are Linux-only",
    )
    def test_abstract_socket(self, monkeypatch, notify_receiver):
        """A NOTIFY_SOCKET starting with '@' is in the abstract namespace"""
        name = f"cloud-init-test-{uuid.uuid4().hex}"
        notify_receiver.bind(f"\0{name}")
        monkeypatch.setenv("NOTIFY_SOCKET", f"@{name}")
        ci_socket.sd_notify("READY=1")
        assert b"READY=1" == notify_receiver.recv(4096)

    def test_unsupported_socket_type(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_SOCKET", "vsock:2:1234")
        with pytest.raises(OSError, match="Unsupported socket type"):
            ci_socket.sd_notify("READY=1")
