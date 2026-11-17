import json
import pickle
from typing import Any, Dict, Union
from unittest import mock

import pytest

from cloudinit import sources
from cloudinit.sources import DataSourceOpenStack as ds

openstack_ds_name = ds.DataSourceOpenStack.dsname.lower()


class _NetworkConfigCachingDataSource(sources.DataSource):
    """Minimal datasource declaring the conventional cache attribute."""

    _network_config: Union[Dict[str, Any], None, sources.Unset] = sources.UNSET

    def _get_data(self) -> bool:
        return True


class TestUnsetSentinel:
    """sources.UNSET marks invalidated caches; never a valid config value."""

    def test_unset_is_falsy(self):
        """An invalidated cache must not look like valid configuration."""
        assert not sources.UNSET
        assert not bool(sources.UNSET)

    def test_unset_string_equality(self):
        """UNSET equals the plain "_unset" string, in either direction."""
        assert sources.UNSET == "_unset"
        assert "_unset" == sources.UNSET
        assert sources.UNSET != {}
        assert {} != sources.UNSET

    def test_unset_repr(self):
        assert repr(sources.UNSET) == "UNSET"

    def test_unset_json_serializes_as_plain_string(self):
        assert json.dumps(sources.UNSET) == '"_unset"'

    def test_unset_pickles_as_plain_string(self):
        """obj.pkl compatibility: the sentinel pickles as the plain
        "_unset" string so caches remain readable by older releases."""
        unpickled = pickle.loads(pickle.dumps(sources.UNSET))
        assert unpickled == "_unset"
        assert unpickled == sources.UNSET

    def test_legacy_plain_string_cache_value_equals_unset(self):
        """Plain "_unset" strings read from obj.pkl caches written by
        older releases are still recognized as the invalidated state."""
        legacy = pickle.loads(pickle.dumps("_unset"))
        assert legacy == sources.UNSET
        assert not legacy != sources.UNSET

    def test_clear_cached_attrs_invalidated_config_is_falsy(self):
        """A network config cache invalidated via clear_cached_attrs is falsy.

        Assert `if cached:` guards cannot mistake it for valid configuration.
        """
        datasource = _NetworkConfigCachingDataSource(
            sys_cfg={}, distro=mock.MagicMock(), paths=mock.MagicMock()
        )
        setattr(datasource, "_network_config", {"version": 2})
        datasource._dirty_cache = True
        datasource.clear_cached_attrs((("_network_config", sources.UNSET),))
        assert datasource._network_config == sources.UNSET
        assert not datasource._network_config


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
