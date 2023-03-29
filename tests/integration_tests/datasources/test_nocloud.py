"""NoCloud datasource integration tests."""
import pytest
from pycloudlib.lxd.instance import LXDInstance

from cloudinit.subp import subp
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM

VENDOR_DATA = """\
#cloud-config
runcmd:
  - touch /var/tmp/seeded_vendordata_test_file
"""


LXD_METADATA_NOCLOUD_SEED = """\
  /var/lib/cloud/seed/nocloud-net/meta-data:
    when:
    - create
    - copy
    create_only: false
    template: emptycfg.tpl
    properties:
      default: |
        #cloud-config
        {}
  /var/lib/cloud/seed/nocloud-net/user-data:
    when:
    - create
    - copy
    create_only: false
    template: emptycfg.tpl
    properties:
      default: |
        #cloud-config
        {}
"""


def setup_nocloud(instance: LXDInstance):
    # On Jammy and above, LXD no longer uses NoCloud, so we need to set
    # it up manually
    lxd_image_metadata = subp(
        ["lxc", "config", "metadata", "show", instance.name]
    )
    if "/var/lib/cloud/seed/nocloud-net" in lxd_image_metadata.stdout:
        return
    subp(
        ["lxc", "config", "template", "create", instance.name, "emptycfg.tpl"],
    )
    subp(
        ["lxc", "config", "template", "edit", instance.name, "emptycfg.tpl"],
        data="#cloud-config\n{}\n",
    )
    subp(
        ["lxc", "config", "metadata", "edit", instance.name],
        data=f"{lxd_image_metadata.stdout}{LXD_METADATA_NOCLOUD_SEED}",
    )


@pytest.mark.lxd_setup.with_args(setup_nocloud)
@pytest.mark.lxd_use_exec
@pytest.mark.skipif(
    PLATFORM != "lxd_container",
    reason="Requires NoCloud with custom setup",
)
def test_nocloud_seedfrom_vendordata(client: IntegrationInstance):
    """Integration test for #570.

    Test that we can add optional vendor-data to the seedfrom file in a
    NoCloud environment
    """
    seed_dir = "/var/tmp/test_seed_dir"
    result = client.execute(
        "mkdir {seed_dir} && "
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
