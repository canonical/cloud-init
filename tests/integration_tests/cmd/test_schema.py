"""Tests for `cloud-init status`"""
from textwrap import dedent

from tests.integration_tests.instances import IntegrationInstance


def test_schema_deprecations(client: IntegrationInstance):
    """Test schema behavior with deprecated configs."""
    DEPRECATED_DATA = dedent(
        """\
    #cloud-config
    apt_update: false
    apt_upgrade: false
    apt_reboot_if_required: false
    """
    )
    user_data_fn = "/root/user-data"
    client.write_to_file(user_data_fn, DEPRECATED_DATA)

    result = client.execute(f"cloud-init schema --config-file {user_data_fn}")
    assert result.ok, "`schema` cmd must return 0 even with deprecated configs"
    assert not result.stderr
    assert "Cloud config schema deprecations:" in result.stdout
    assert "apt_update: DEPRECATED" in result.stdout
    assert "apt_upgrade: DEPRECATED" in result.stdout
    assert "apt_reboot_if_required: DEPRECATED" in result.stdout

    annotated_result = client.execute(
        f"cloud-init schema --annotate --config-file {user_data_fn}"
    )
    assert (
        annotated_result.ok
    ), "`schema` cmd must return 0 even with deprecated configs"
    assert not annotated_result.stderr
    expected_output = dedent(
        """\
        #cloud-config
        apt_update: false\t\t# D1
        apt_upgrade: false\t\t# D2
        apt_reboot_if_required: false\t\t# D3

        # Deprecations: -------------
        # D1: DEPRECATED. Dropped in EOL Ubuntu bionic. Use ``package_update``. Default: ``false``
        # D2: DEPRECATED. Dropped in EOL Ubuntu bionic. Use ``package_upgrade``. Default: ``false``
        # D3: DEPRECATED. Dropped in EOL Ubuntu bionic. Use ``package_reboot_if_required``. Default: ``false``


        Valid cloud-config: /root/user-data"""  # noqa: E501
    )
    assert expected_output in annotated_result.stdout
