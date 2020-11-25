"""Integration test for the timezone module.

This test specifies a timezone to be used by the ``timezone`` module
and then checks that if that timezone was respected during boot.

(This is ported from
``tests/cloud_tests/testcases/modules/timezone.yaml``.)"""

import pytest


USER_DATA = """\
#cloud-config
timezone: US/Aleutian
"""


@pytest.mark.ci
class TestTimezone:

    @pytest.mark.user_data(USER_DATA)
    def test_timezone(self, client):
        timezone_output = client.execute(
            'date "+%Z" --date="Thu, 03 Nov 2016 00:47:00 -0400"')
        assert timezone_output.strip() == "HDT"
