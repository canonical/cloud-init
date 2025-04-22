import os
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def mock_util_get_cmdline():
    with mock.patch("cloudinit.util.get_cmdline", return_value="") as m:
        yield m


@pytest.fixture(autouse=True)
def hide_resource_disk():
    """GitHub runner may have a resource disk which may affect tests."""
    real_exists = os.path.exists
    with mock.patch("os.path.exists") as mock_exists:
        mock_exists.side_effect = lambda path: (
            False
            if path == "/dev/disk/cloud/azure_resource"
            else real_exists(path)
        )
        yield
