"""NoCloud datasource integration tests."""
import tempfile
from pathlib import Path

import pytest
from pycloudlib.lxd.instance import LXDInstance

from cloudinit.subp import subp
from tests.integration_tests.clouds import ImageSpecification
from tests.integration_tests.instances import IntegrationInstance

VENDOR_DATA = """\
#cloud-config
runcmd:
  - touch /var/tmp/seeded_vendordata_test_file
"""


def setup_nocloud(instance: LXDInstance):
    # On Jammy and above, LXD no longer uses NoCloud, so we need to set
    # it up manually
    if ImageSpecification.from_os_image().release in [
        "bionic",
        "focal",
        "impish",
    ]:
        return
    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        userdata_file = tmpdir / "user-data"
        metadata_file = tmpdir / "meta-data"
        userdata_file.touch()
        metadata_file.touch()
        subp(
            [
                "lxc",
                "file",
                "push",
                str(userdata_file),
                str(metadata_file),
                f"{instance.name}/var/lib/cloud/seed/nocloud-net/",
                "--create-dirs",
            ]
        )


# Only running on LXD container because we need NoCloud with custom setup
@pytest.mark.lxd_container
@pytest.mark.lxd_setup.with_args(setup_nocloud)
@pytest.mark.lxd_use_exec
def test_nocloud_seedfrom_vendordata(client: IntegrationInstance):
    """Integration test for #570.

    Test that we can add optional vendor-data to the seedfrom file in a
    NoCloud environment
    """
    seed_dir = "/var/tmp/test_seed_dir"
    result = client.execute(
        "mkdir {seed_dir} && "
        "mkdir -p /var/lib/cloud/seed/nocloud-net && "
        "touch {seed_dir}/user-data && "
        "touch {seed_dir}/meta-data && "
        "echo 'seedfrom: {seed_dir}/' > "
        "/var/lib/cloud/seed/nocloud-net/meta-data".format(seed_dir=seed_dir)
    )
    assert result.return_code == 0

    client.write_to_file(
        "{}/vendor-data".format(seed_dir),
        VENDOR_DATA,
    )
    client.execute("cloud-init clean --logs")
    client.restart()
    assert client.execute("cloud-init status").ok
    assert "seeded_vendordata_test_file" in client.execute("ls /var/tmp")
