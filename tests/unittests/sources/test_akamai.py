from contextlib import suppress
from typing import Any, Dict, List, Optional, Union

import pytest

from cloudinit.sources.DataSourceAkamai import (
    DataSourceAkamai,
    DataSourceAkamaiLocal,
    MetadataAvailabilityResult,
)
from tests.unittests.helpers import mock


class TestDataSourceAkamai:
    """
    Test cases for DataSourceAkamai
    """

    def _get_datasource(
        self, ds_cfg: Optional[Dict[str, Any]] = None, local: bool = False
    ) -> Union[DataSourceAkamai, DataSourceAkamaiLocal]:
        """
        Creates a test DataSource configured as provided
        """
        if ds_cfg is None:
            ds_cfg = {}

        # set up our system config with the config provided here
        sys_cfg = {
            "datasource": {
                "Akamai": ds_cfg,
            }
        }

        # patch read_dmi_data, even when not in a container
        with mock.patch(
            "cloudinit.dmi.read_dmi_data",
            return_value="",
        ):
            if local:
                ds: Union[
                    DataSourceAkamai, DataSourceAkamaiLocal
                ] = DataSourceAkamaiLocal(sys_cfg, None, None)
            else:
                ds = DataSourceAkamai(sys_cfg, None, None)

        return ds

    @pytest.mark.parametrize(
        "path_name,use_v6,ds_cfg,expected_url",
        (
            # normal paths
            ("token", False, {}, "http://169.254.169.254/v1/token"),
            ("metadata", False, {}, "http://169.254.169.254/v1/instance"),
            ("userdata", False, {}, "http://169.254.169.254/v1/user-data"),
            # normal paths, force v6
            ("metadata", True, {}, "http://[fd00:a9fe:a9fe::1]/v1/instance"),
            ("token", True, {}, "http://[fd00:a9fe:a9fe::1]/v1/token"),
            ("userdata", True, {}, "http://[fd00:a9fe:a9fe::1]/v1/user-data"),
            # overrides
            (
                "token",
                False,
                {"allow_ipv4": False},
                "http://[fd00:a9fe:a9fe::1]/v1/token",
            ),
            (
                "token",
                False,
                {"paths": {"token": "/changed"}},
                "http://169.254.169.254/changed",
            ),
            (
                "token",
                False,
                {"base_urls": {"ipv4": "http://12.34.56.78"}},
                "http://12.34.56.78/v1/token",
            ),
        ),
    )
    def test_build_url(
        self,
        path_name: str,
        use_v6: bool,
        ds_cfg: Dict[str, Any],
        expected_url: str,
    ):
        """
        Tests that _build_url returns the expected URLs for various
        configurations
        """
        ds = self._get_datasource(ds_cfg=ds_cfg)
        result = ds._build_url(path_name, use_v6=use_v6)
        assert (
            result == expected_url
        ), f"Unexpected URL {result} for {path_name}"

    @pytest.mark.parametrize(
        "local_stage,ds_cfg,expected_result",
        (
            # normal config
            (True, {}, MetadataAvailabilityResult.AVAILABLE),
            (False, {}, MetadataAvailabilityResult.AVAILABLE),
            # disable dhcp
            (
                True,
                {"allow_dhcp": False},
                MetadataAvailabilityResult.AVAILABLE,
            ),
            (
                True,
                {"allow_dhcp": False, "allow_ipv6": False},
                MetadataAvailabilityResult.DEFER,
            ),
            (
                False,
                {"allow_dhcp": False},
                MetadataAvailabilityResult.AVAILABLE,
            ),
            (
                False,
                {"allow_dhcp": False, "allow_ipv6": False},
                MetadataAvailabilityResult.AVAILABLE,
            ),
            # disable stages
            (
                True,
                {"allow_local_stage": False},
                MetadataAvailabilityResult.DEFER,
            ),
            (
                False,
                {"allow_local_stage": False},
                MetadataAvailabilityResult.AVAILABLE,
            ),
            (
                True,
                {"allow_init_stage": False},
                MetadataAvailabilityResult.AVAILABLE,
            ),
            (
                False,
                {"allow_init_stage": False},
                MetadataAvailabilityResult.DEFER,
            ),
            # disable all network types
            (
                True,
                {"allow_ipv4": False, "allow_ipv6": False},
                MetadataAvailabilityResult.NOT_AVAILABLE,
            ),
            (
                False,
                {"allow_ipv4": False, "allow_ipv6": False},
                MetadataAvailabilityResult.NOT_AVAILABLE,
            ),
            # disable all stages
            (
                True,
                {"allow_local_stage": False, "allow_init_stage": False},
                MetadataAvailabilityResult.NOT_AVAILABLE,
            ),
            (
                False,
                {"allow_local_stage": False, "allow_init_stage": False},
                MetadataAvailabilityResult.NOT_AVAILABLE,
            ),
        ),
    )
    def test_should_fetch_data(
        self, local_stage: bool, ds_cfg: Dict[str, Any], expected_result: bool
    ):
        """
        Tests if _should_fetch_data returns the expected values based on the
        configuration of the DataSource
        """
        ds = self._get_datasource(ds_cfg=ds_cfg, local=local_stage)
        result = ds._should_fetch_data()

        assert (
            result == expected_result
        ), f"Unexpected result '{result}' for should fetch data!"

    @pytest.mark.parametrize(
        "local_stage,ds_cfg,expected_manager_config,expected_interface",
        (
            # local stage - these use context managers
            (
                True,
                {},
                [((False, True), True), ((True, False), False)],
                "eth0",
            ),
            (True, {"allow_ipv4": False}, [((False, True), True)], "eth0"),
            (True, {"allow_ipv6": False}, [((True, False), False)], "eth0"),
            (True, {"allow_ipv4": False, "allow_ipv6": False}, [], "eth0"),
            (
                True,
                {"preferred_mac_prefixes": ["12:34:"]},
                [((False, True), True), ((True, False), False)],
                "eth1",
            ),
            # init stage - these use the noop suppress
            (False, {}, [(None, True), (None, False)], "eth0"),
            (False, {"allow_ipv4": False}, [(None, True)], "eth0"),
            (False, {"allow_ipv6": False}, [(None, False)], "eth0"),
            (
                False,
                {"allow_ipv4": False, "allow_ipv6": False},
                [],
                "eth0",
            ),
            (
                False,
                {"preferred_mac_prefixes": ["12:34:"]},
                [(None, True), (None, False)],
                "eth1",
            ),
        ),
    )
    @mock.patch("cloudinit.sources.DataSourceAkamai.get_interfaces_by_mac")
    def test_get_network_context_managers(
        self,
        get_interfaces_by_mac,
        local_stage: bool,
        ds_cfg: Dict[str, Any],
        expected_manager_config: List,
        expected_interface: str,
    ):
        """
        Tests that _get_network_context_managers returns the expected set of
        context managers
        """
        ds = self._get_datasource(ds_cfg=ds_cfg, local=local_stage)

        # set up fake mac addresses for our interfaces
        get_interfaces_by_mac.return_value = {
            "f2:3a:bc:de:f0:12": "eth0",
            "12:34:56:78:90:ab": "eth1",
        }

        result = ds._get_network_context_managers()

        assert len(result) == len(
            expected_manager_config
        ), f"Expected {len(expected_manager_config)}, got {result}"

        # make sure the results are what we expected
        for rx, ex in zip(result, expected_manager_config):
            r, rv6 = rx
            e, ev6 = ex
            if e is None:
                assert isinstance(
                    r, suppress
                ), f"Expected contextlib.suppress, got {r}"
                assert rv6 == ev6
            else:
                ipv4, ipv6 = e
                assert r.ipv4 == ipv4, f"Expected {r} to support ipv4"
                assert r.ipv6 == ipv6, f"Expected {r} to support ipv6"
                assert rv6 == ev6

    @pytest.mark.parametrize(
        "use_v6",
        (
            False,
            True,
        ),
    )
    @mock.patch("cloudinit.url_helper.readurl")
    def test_fetch_metadata(self, readurl, use_v6: bool):
        """
        Tests that making requests sends the expected requests in the expected
        order
        """
        # the responses, in the order we expect the calls
        readurl.side_effect = [
            # to PUT /v1/token
            mock.MagicMock(code=200, __str__=lambda _: "test-token"),
            # to GET /v1/instance; truncated for brevity
            '{"id": 123}',
            # to GET /v1/user-data
            "",
        ]

        # if we're asked to force using v6, we should see the hostname of the
        # urls change
        host = "[fd00:a9fe:a9fe::1]" if use_v6 else "169.254.169.254"

        ds = self._get_datasource()
        ds._fetch_metadata(use_v6=use_v6)

        assert readurl.call_count == 3
        assert ds.metadata == {"id": 123}
        assert ds.userdata_raw == ""

        assert readurl.mock_calls == [
            mock.call(
                f"http://{host}/v1/token",
                request_method="PUT",
                timeout=30,
                sec_between=2,
                retries=4,
                headers={
                    "Metadata-Token-Expiry-Seconds": "300",
                },
            ),
            mock.call(
                f"http://{host}/v1/instance",
                timeout=30,
                sec_between=2,
                retries=2,
                headers={
                    "Accept": "application/json",
                    "Metadata-Token": "test-token",
                },
            ),
            mock.call(
                f"http://{host}/v1/user-data",
                timeout=30,
                sec_between=2,
                retries=2,
                headers={
                    "Metadata-Token": "test-token",
                },
            ),
        ]
