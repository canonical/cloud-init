import pytest

from tests.integration_tests import releases, util
from tests.integration_tests.instances import IntegrationInstance


def setup_custom_datasource(client: IntegrationInstance, datasource_name: str):
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/99-imds.cfg",
        f"datasource_list: [ {datasource_name}, None ]\n"
        "datasource_pkg_list: [ cisources ]",
    )
    assert client.execute("mkdir -p /usr/lib/python3/dist-packages/cisources")
    client.push_file(
        util.ASSETS_DIR / f"DataSource{datasource_name}.py",
        "/usr/lib/python3/dist-packages/cisources/"
        f"DataSource{datasource_name}.py",
    )
    # Since our custom datasource isn't handling networking, disable
    # cloud-init networking to avoid wait-online timeouts and errors
    client.write_to_file(
        "/etc/cloud/cloud.cfg.d/99-disable-networking.cfg",
        "network: {config: disabled}",
    )


def verify_no_cache_boot(client: IntegrationInstance):
    log = client.read_from_file("/var/log/cloud-init.log")
    util.verify_ordered_items_in_text(
        [
            "No local datasource found",
            "running 'init'",
            "no cache found",
            "Detected DataSource",
            "TEST _get_data called",
        ],
        text=log,
    )
    util.verify_clean_boot(client)


@pytest.mark.skipif(
    not releases.IS_UBUNTU,
    reason="hardcoded dist-packages directory",
)
def test_no_cache_network_only(client: IntegrationInstance):
    """Test cache removal per boot. GH-5486

    This tests the CloudStack password reset use case. The expectation is:
    - Metadata is fetched in network timeframe only
    - Because `check_instance_id` is not defined, no cached datasource
      is found in the init-local phase, but the cache is used in the
      remaining phases due to existence of /run/cloud-init/.instance-id
    - Because `check_if_fallback_is_allowed` is not defined, cloud-init
      does NOT fall back to the pickled datasource, and will
      instead delete the cache during the init-local phase
    - Metadata is therefore fetched every boot in the network phase
    """
    setup_custom_datasource(client, "NoCacheNetworkOnly")

    # Run cloud-init as if first boot
    assert client.execute("cloud-init clean --logs")
    client.restart()

    verify_no_cache_boot(client)

    # Clear the log without clean and run cloud-init for subsequent boot
    assert client.execute("echo '' > /var/log/cloud-init.log")
    client.restart()

    verify_no_cache_boot(client)


@pytest.mark.skipif(
    not releases.IS_UBUNTU,
    reason="hardcoded dist-packages directory",
)
def test_no_cache_with_fallback(client: IntegrationInstance):
    """Test we use fallback when defined and no cache available."""
    setup_custom_datasource(client, "NoCacheWithFallback")

    # Run cloud-init as if first boot
    assert client.execute("cloud-init clean --logs")
    # Used by custom datasource
    client.execute("touch /ci-test-firstboot")
    client.restart()

    log = client.read_from_file("/var/log/cloud-init.log")
    util.verify_ordered_items_in_text(
        [
            "no cache found",
            "Detected DataSource",
            "TEST _get_data called",
            "running 'init'",
            "restored from cache with run check",
            "running 'modules:config'",
        ],
        text=log,
    )
    util.verify_clean_boot(client)

    # Clear the log without clean and run cloud-init for subsequent boot
    assert client.execute("echo '' > /var/log/cloud-init.log")
    client.execute("rm /ci-test-firstboot")
    client.restart()

    log = client.read_from_file("/var/log/cloud-init.log")
    util.verify_ordered_items_in_text(
        [
            "cache invalid in datasource",
            "Detected DataSource",
            "Restored fallback datasource from checked cache",
            "running 'init'",
            "restored from cache with run check",
            "running 'modules:config'",
        ],
        text=log,
    )
    util.verify_clean_boot(client)
