from pathlib import Path

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import ASSETS_DIR, verify_clean_log

PICKLE_PATH = Path("/var/lib/cloud/instance/obj.pkl")
TEST_PICKLE = ASSETS_DIR / "test_version_change.pkl"


def _assert_no_pickle_problems(log):
    assert "Failed loading pickled blob" not in log
    verify_clean_log(log)


def test_reboot_without_version_change(client: IntegrationInstance):
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Python version change detected" not in log
    assert "Cache compatibility status is currently unknown." not in log
    _assert_no_pickle_problems(log)

    client.restart()
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Python version change detected" not in log
    assert "Could not determine Python version used to write cache" not in log
    _assert_no_pickle_problems(log)

    # Now ensure that loading a bad pickle gives us problems
    client.push_file(TEST_PICKLE, PICKLE_PATH)
    client.restart()
    log = client.read_from_file("/var/log/cloud-init.log")

    # no cache found is an "expected" upgrade error, and
    # "Failed" means we're unable to load the pickle
    assert any(
        [
            "Failed loading pickled blob from {}".format(PICKLE_PATH) in log,
            "no cache found" in log,
        ]
    )


@pytest.mark.ec2
@pytest.mark.gce
@pytest.mark.oci
@pytest.mark.openstack
@pytest.mark.lxd_container
@pytest.mark.lxd_vm
# No Azure because the cache gets purged every reboot, so we'll never
# get to the point where we need to purge cache due to version change
def test_cache_purged_on_version_change(client: IntegrationInstance):
    # Start by pushing the invalid pickle so we'll hit an error if the
    # cache didn't actually get purged
    client.push_file(TEST_PICKLE, PICKLE_PATH)
    client.execute("echo '1.0' > /var/lib/cloud/data/python-version")
    client.restart()
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Python version change detected. Purging cache" in log
    _assert_no_pickle_problems(log)


def test_log_message_on_missing_version_file(client: IntegrationInstance):
    # Start by pushing a pickle so we can see the log message
    client.push_file(TEST_PICKLE, PICKLE_PATH)
    client.execute("rm /var/lib/cloud/data/python-version")
    client.execute("rm /var/log/cloud-init.log")
    client.restart()
    log = client.read_from_file("/var/log/cloud-init.log")
    if "no cache found" not in log:
        # We don't expect the python version file to exist if we have no
        # pre-existing cache
        assert (
            "Writing python-version file. "
            "Cache compatibility status is currently unknown." in log
        )
