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
        # test ci.datasource=
        ("aosiejfoij ci.datasource=OpenStack ", openstack_ds_name),
        ("ci.datasource=OpenStack", openstack_ds_name),
        ("aosiejfoij ci.datasource=OpenStack blah", openstack_ds_name),
        ("aosiejfoij ci.datasource=OpenStack faljskebflk", openstack_ds_name),
        ("ci.datasource=OpenStack;", openstack_ds_name),
        ("ci.datasource=openstack;", openstack_ds_name),
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
    ),
)
def test_ds_detect_kernel_commandline(m_cmdline, expected_ds):
    """check commandline match"""
    with mock.patch(
        "cloudinit.util.get_cmdline",
        return_value=m_cmdline,
    ):
        assert (
            expected_ds == sources.parse_cmdline().lower()
        ), f"could not parse [{m_cmdline}]"
