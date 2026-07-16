import logging

import pytest

from cloudinit import lifecycle

LOG = logging.getLogger()


class TestLogWithDowngradableLevel:
    @pytest.mark.parametrize(
        "version,expected",
        [
            ("9", logging.ERROR),
            ("11", logging.DEBUG),
        ],
    )
    def test_log_with_downgradable_level(
        self, mocker, caplog, version, expected
    ):
        mocker.patch("cloudinit.features.DEPRECATION_INFO_BOUNDARY", "10")
        lifecycle.log_with_downgradable_level(
            logger=LOG,
            version=version,
            requested_level=logging.ERROR,
            msg="look at me %s %s!",
            args=("one", "two"),
        )
        records = caplog.record_tuples
        assert len(records) == 1
        assert records[0][1] == expected
        assert records[0][2] == "look at me one two!"
