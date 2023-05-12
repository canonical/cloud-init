from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def mock_util_get_cmdline():
    with mock.patch("cloudinit.util.get_cmdline", return_value="") as m:
        yield m
