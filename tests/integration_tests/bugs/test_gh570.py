"""Integration test for #570.

Test that we can add optional vendor-data to the seedfrom file in a
NoCloud environment
"""

from tests.integration_tests.instances import IntegrationInstance
import pytest

VENDOR_DATA = """\
#cloud-config
runcmd:
  - touch /var/tmp/seeded_vendordata_test_file
"""


# Only running on LXD because we need NoCloud for this test
@pytest.mark.sru_2020_11
@pytest.mark.lxd_container
@pytest.mark.lxd_vm
def test_nocloud_seedfrom_vendordata(client: IntegrationInstance):
    seed_dir = '/var/tmp/test_seed_dir'
    result = client.execute(
        "mkdir {seed_dir} && "
        "touch {seed_dir}/user-data && "
        "touch {seed_dir}/meta-data && "
        "echo 'seedfrom: {seed_dir}/' > "
        "/var/lib/cloud/seed/nocloud-net/meta-data".format(seed_dir=seed_dir)
    )
    assert result.return_code == 0

    client.write_to_file(
        '{}/vendor-data'.format(seed_dir),
        VENDOR_DATA,
    )
    client.execute('cloud-init clean --logs')
    client.restart()
    assert client.execute('cloud-init status').ok
    assert 'seeded_vendordata_test_file' in client.execute('ls /var/tmp')
