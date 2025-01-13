"""cloudinit.signal_handler tests"""

import inspect
import signal
from unittest.mock import Mock, patch

import pytest

from cloudinit import signal_handler

REENTRANT = "reentrant"


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
    @pytest.mark.parametrize(
        "m_suspended",
        [
            (REENTRANT, 0),
            (True, 0),
            (False, 1),
        ],
    )
    def test_suspend_signal(self, m_args, m_suspended):
        """suspend_crash should prevent crashing (exit 1) on signal

        otherwise cloud-init should exit 1
        """
        sig, frame = m_args
        suspended, rc = m_suspended

        with patch.object(signal_handler.sys, "exit", Mock()) as m_exit:
            if suspended is True:
                with signal_handler.suspend_crash():
                    signal_handler._handle_exit(sig, frame)
            elif suspended == REENTRANT:
                with signal_handler.suspend_crash():
                    with signal_handler.suspend_crash():
                        signal_handler._handle_exit(sig, frame)
            else:
                signal_handler._handle_exit(sig, frame)
        m_exit.assert_called_with(rc)
