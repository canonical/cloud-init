# This file is part of cloud-init. See LICENSE file for license information.
"""Test the behavior of loading/discarding pickle data"""
from pathlib import Path

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import (
    ASSETS_DIR,
    verify_ordered_items_in_text,
)

PICKLE_PATH = Path("/var/lib/cloud/instance/obj.pkl")
TEST_PICKLE = ASSETS_DIR / "trusty_with_mime.pkl"


@pytest.mark.lxd_container
def test_log_message_on_missing_version_file(client: IntegrationInstance):
    client.push_file(TEST_PICKLE, PICKLE_PATH)
    client.restart()
    assert client.execute("cloud-init status --wait").ok
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_ordered_items_in_text(
        [
            "Unable to unpickle datasource: 'MIMEMultipart' object has no "
            "attribute 'policy'. Ignoring current cache.",
            "no cache found",
            "Searching for local data source",
            "SUCCESS: found local data from DataSourceNoCloud",
        ],
        log,
    )
