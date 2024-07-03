import pytest

from cloudinit import sources
from cloudinit.sources import DataSourceOpenStack as ds
from tests.unittests.helpers import mock

openstack_ds_name = ds.DataSourceOpenStack.dsname.lower()


@pytest.mark.parametrize(
    "m_cmdline, expected_ds",
    (
        # test ci.ds=
        ("aosiejfoij ci.ds=OpenStack ", openstack_ds_name),
        ("ci.ds=OpenStack", openstack_ds_name),
        ("aosiejfoij ci.ds=OpenStack blah", openstack_ds_name),
        ("aosiejfoij ci.ds=OpenStack faljskebflk", openstack_ds_name),
        ("ci.ds=OpenStack;", openstack_ds_name),
        ("ci.ds=openstack;", openstack_ds_name),
        ("notci.ds=somecloud ci.ds=openstack", openstack_ds_name),
        # test ci.datasource=
        ("aosiejfoij ci.datasource=OpenStack ", openstack_ds_name),
        ("ci.datasource=OpenStack", openstack_ds_name),
        ("aosiejfoij ci.datasource=OpenStack blah", openstack_ds_name),
        ("aosiejfoij ci.datasource=OpenStack faljskebflk", openstack_ds_name),
        ("ci.datasource=OpenStack;", openstack_ds_name),
        ("ci.datasource=openstack;", openstack_ds_name),
        ("notci.datasource=0 ci.datasource=nocloud", "nocloud"),
        # weird whitespace
        ("ci.datasource=OpenStack\n", openstack_ds_name),
        ("ci.datasource=OpenStack\t", openstack_ds_name),
        ("ci.datasource=OpenStack\r", openstack_ds_name),
        ("ci.datasource=OpenStack\v", openstack_ds_name),
        ("ci.ds=OpenStack\n", openstack_ds_name),
        ("ci.ds=OpenStack\t", openstack_ds_name),
        ("ci.ds=OpenStack\r", openstack_ds_name),
        ("ci.ds=OpenStack\v", openstack_ds_name),
        ("ci.ds=nocloud-net\v", "nocloud-net"),
        ("ci.datasource=nocloud\v", "nocloud"),
        # test ds=
        ("ds=nocloud-net", "nocloud-net"),
        ("foo ds=nocloud-net bar", "nocloud-net"),
        ("bonding.max_bonds=0", ""),
        ("foo bonding.max_bonds=0 ds=nocloud-net bar", "nocloud-net"),
    ),
)
def test_ds_detect_kernel_command_line(m_cmdline, expected_ds):
    """check command line match"""
    with mock.patch(
        "cloudinit.util.get_cmdline",
        return_value=m_cmdline,
    ):
        assert (
            expected_ds == sources.parse_cmdline().lower()
        ), f"could not parse [{m_cmdline}]"
