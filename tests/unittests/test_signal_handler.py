"""cloudinit.signal_handler tests"""

import re
import signal
import sys

from cloudinit.signal_handler import _handle_exit


class TestSignalHandler:
    """Test signal_handler.py"""

    def test_handle_exit(self, mocker, caplog):
        """Test handle_exit()"""
        mocker.patch("cloudinit.signal_handler.sys.exit")
        mocker.patch("cloudinit.log.log_util.write_to_console")

        frame = sys._getframe()
        _handle_exit(signal.Signals.SIGHUP, frame)

        record = caplog.records[0]
        assert record.levelname == "INFO"
        assert re.match(
            (
                r"Received signal SIGHUP resulting in exit. Cause:\n"
                r"  Filename:.*test_signal_handler.py\n"
                r"  Function: test_handle_exit\n"
                r"  Line number: \d+"
            ),
            record.message,
        )
