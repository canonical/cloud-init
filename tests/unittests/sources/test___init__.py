import pickle
from typing import Optional
from unittest import mock

import pytest

from cloudinit import sources
from cloudinit.sources import DataSourceOpenStack as ds

openstack_ds_name = ds.DataSourceOpenStack.dsname.lower()


class _NetworkConfigDataSource(sources.DataSource):
    """Minimal datasource counting _get_network_config calls per instance.

    network_config caches the dict returned by _get_network_config until
    the cache is invalidated.
    """

    hook_calls: int = 0
    hook_result: Optional[dict] = {"version": 1}

    def _get_data(self) -> bool:
        return True

    def _get_network_config(self) -> Optional[dict]:
        self.hook_calls += 1
        return self.hook_result


class _PicklableHookDataSource(_NetworkConfigDataSource):
    """Pickle shim stripping mocked unpicklable attributes."""

    def __getstate__(self):
        state = super().__getstate__()
        state["distro"] = None
        state["paths"] = None
        state["ud_proc"] = None
        return state


class TestNetworkConfigHook:
    """The base network_config property owns all cache invalidation.

    The cache attribute is a plain Optional[dict]: None marks the cache
    invalidated. Datasources implement _get_network_config and never
    inspect the cache; any invalidated value (None, UNSET, or the plain
    "_unset" string restored from obj.pkl caches written by older
    releases) results in a call to _get_network_config, whose dict
    result is then cached.
    """

    @pytest.fixture
    def datasource(self) -> _NetworkConfigDataSource:
        return _NetworkConfigDataSource(
            sys_cfg={}, distro=mock.MagicMock(), paths=mock.MagicMock()
        )

    def test_hook_result_is_cached(self, datasource):
        """A dict from _get_network_config is cached; the hook runs once."""
        assert {"version": 1} == datasource.network_config
        assert {"version": 1} == datasource.network_config
        assert 1 == datasource.hook_calls
        assert {"version": 1} == datasource._network_config

    def test_invalidated_cache_requires_recompute(self, datasource):
        """update_metadata_if_supported invalidates the cached dict by
        resetting the cache to None, requiring _get_network_config to run
        again on next access."""
        assert {"version": 1} == datasource.network_config
        datasource._dirty_cache = True
        datasource.clear_cached_attrs((("_network_config", None),))
        assert datasource._network_config is None
        assert {"version": 1} == datasource.network_config
        assert 2 == datasource.hook_calls

    def test_invalidated_cache_is_never_returned(self, datasource):
        """A None cache is regenerated via the hook, never returned to
        callers as if it were configuration."""
        datasource._network_config = None
        assert {"version": 1} == datasource.network_config
        assert 1 == datasource.hook_calls

    def test_legacy_unset_string_requires_recompute(self, datasource):
        """The plain "_unset" string restored from obj.pkl caches
        written by older releases is treated as invalidated, never as
        valid configuration."""
        datasource._network_config = "_unset"
        assert {"version": 1} == datasource.network_config
        assert 1 == datasource.hook_calls

    def test_none_result_is_returned_without_caching(self, datasource):
        """A None hook result is a valid final "no config" answer which is
        not cached; later accesses regenerate it."""
        datasource.hook_result = None
        assert None is datasource.network_config
        assert None is datasource.network_config
        assert None is datasource._network_config
        assert 2 == datasource.hook_calls

    def test_default_hook_returns_none(self):
        """A datasource which does not implement the hook has no config."""
        no_config_ds = sources.DataSource(
            sys_cfg={}, distro=mock.MagicMock(), paths=mock.MagicMock()
        )
        assert None is no_config_ds.network_config
        assert None is no_config_ds.network_config

    def test_invalidated_cache_pickles_to_none_for_old_releases(self):
        """An invalidated cache pickles as None so obj.pkl caches remain
        readable by older releases, which treat None as an invalid cache
        requiring regeneration; this release regenerates configuration
        from the hook after restore."""
        datasource = _PicklableHookDataSource(
            sys_cfg={}, distro=mock.MagicMock(), paths=mock.MagicMock()
        )
        datasource._dirty_cache = True
        datasource.clear_cached_attrs((("_network_config", None),))
        restored = pickle.loads(pickle.dumps(datasource))
        assert None is restored._network_config
        assert {"version": 1} == restored.network_config
        assert 1 == restored.hook_calls


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
