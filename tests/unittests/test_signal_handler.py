"""cloudinit.signal_handler tests"""

import inspect
import signal
from unittest.mock import Mock, patch

import pytest

from cloudinit import signal_handler


@patch.object(signal_handler.sys, "exit", Mock())
class TestSignalHandler:

    @pytest.mark.parametrize(
        "m_args",
        [
            (signal.SIGINT, inspect.currentframe()),
            (9, None),
            (signal.SIGTERM, None),
            (1, inspect.currentframe()),
        ],
    )
    def test_suspend_signal(self, m_args):
        sig, frame = m_args
        with signal_handler.suspend_crash():
            signal_handler._handle_exit(sig, frame)
