"""Integration test for the apt module's ``sources_list`` functionality.

This test specifies a ``sources_list`` and then checks that (a) the expected
number of sources.list entries is present, and (b) that each expected line
appears in the file.

(This is ported from
``tests/cloud_tests/testcases/modules/apt_configure_sources_list.yaml``.)"""
import re

import pytest


USER_DATA = """\
#cloud-config
apt:
  primary:
    - arches: [default]
      uri: http://archive.ubuntu.com/ubuntu
  security:
    - arches: [default]
      uri: http://security.ubuntu.com/ubuntu
  sources_list: |
    deb $MIRROR $RELEASE main restricted
    deb-src $MIRROR $RELEASE main restricted
    deb $PRIMARY $RELEASE universe restricted
    deb-src $PRIMARY $RELEASE universe restricted
    deb $SECURITY $RELEASE-security multiverse
    deb-src $SECURITY $RELEASE-security multiverse
"""

EXPECTED_REGEXES = [
    r"deb http://archive.ubuntu.com/ubuntu [a-z].* main restricted",
    r"deb-src http://archive.ubuntu.com/ubuntu [a-z].* main restricted",
    r"deb http://archive.ubuntu.com/ubuntu [a-z].* universe restricted",
    r"deb-src http://archive.ubuntu.com/ubuntu [a-z].* universe restricted",
    r"deb http://security.ubuntu.com/ubuntu [a-z].*security multiverse",
    r"deb-src http://security.ubuntu.com/ubuntu [a-z].*security multiverse",
]


@pytest.mark.ci
class TestAptConfigureSourcesList:

    @pytest.mark.user_data(USER_DATA)
    def test_sources_list(self, client):
        sources_list = client.read_from_file("/etc/apt/sources.list")
        assert 6 == len(sources_list.rstrip().split('\n'))

        for expected_re in EXPECTED_REGEXES:
            assert re.search(expected_re, sources_list) is not None
