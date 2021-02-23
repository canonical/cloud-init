"""Integration test for the random seed module.

This test specifies a command to be executed by the ``seed_random`` module, by
providing a different data to be used as seed data. We will then check
if that seed data was actually used.

(This is ported from
``tests/cloud_tests/testcases/modules/seed_random_data.yaml``.)"""

import pytest


USER_DATA = """\
#cloud-config
random_seed:
  data: 'MYUb34023nD:LFDK10913jk;dfnk:Df'
  encoding: raw
  file: /root/seed
"""


@pytest.mark.ci
class TestSeedRandomData:

    @pytest.mark.user_data(USER_DATA)
    def test_seed_random_data(self, client):
        # Only read the first 31 characters, because the rest could be
        # binary data
        result = client.execute("head -c 31 < /root/seed")
        assert result.startswith("MYUb34023nD:LFDK10913jk;dfnk:Df")
