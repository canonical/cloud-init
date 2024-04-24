import pytest


class TestLogExc:
    def test_logexc(self, caplog):
        with pytest.raises(Exception):
            _ = 1 / 0

        assert caplog.record_tuples == []
