import pytest

from cloudinit import sources
from cloudinit.sources import DataSourceOpenStack as ds
from tests.unittests.helpers import mock


@pytest.mark.parametrize(
    "m_cmdline",
    (
        # test ci.ds=
        "aosiejfoij ci.ds=OpenStack ",
        "ci.ds=OpenStack",
        "aosiejfoij ci.ds=OpenStack blah",
        "aosiejfoij ci.ds=OpenStack faljskebflk",
        "ci.ds=OpenStack;",
        "ci.ds=openstack;",
        # test ci.datasource=
        "aosiejfoij ci.datasource=OpenStack ",
        "ci.datasource=OpenStack",
        "aosiejfoij ci.datasource=OpenStack blah",
        "aosiejfoij ci.datasource=OpenStack faljskebflk",
        "ci.datasource=OpenStack;",
        "ci.datasource=openstack;",
        # weird whitespace
        "ci.datasource=OpenStack\n",
        "ci.datasource=OpenStack\t",
        "ci.datasource=OpenStack\r",
        "ci.datasource=OpenStack\v",
        "ci.ds=OpenStack\n",
        "ci.ds=OpenStack\t",
        "ci.ds=OpenStack\r",
        "ci.ds=OpenStack\v",
    ),
)
def test_ds_detect_kernel_commandline(m_cmdline):
    """check commandline match"""
    with mock.patch(
        "cloudinit.util.get_cmdline",
        return_value=m_cmdline,
    ):
        assert (
            ds.DataSourceOpenStack.dsname.lower()
            == sources.parse_cmdline().lower()
        ), f"could not parse [{m_cmdline}]"
