import logging
from unittest import mock

from pycloudlib.errors import PycloudlibTimeoutError
from pycloudlib.lxd.instance import LXDInstance

from tests.integration_tests.instances import IntegrationInstance


def test_keep_instance_when_ip_lookup_fails():
    settings = mock.Mock()
    settings.KEEP_INSTANCE = True

    instance = mock.create_autospec(LXDInstance, instance=True)
    instance.execute_via_ssh = True

    type(instance).ip = mock.PropertyMock(
        side_effect=PycloudlibTimeoutError(
            "Unable to determine IP address after 150 retries."
        )
    )
    cloud = mock.Mock()

    client = IntegrationInstance(
        cloud=cloud,
        instance=instance,
        settings=settings,
    )
    with client:
        pass
    cloud.reaper.reap.assert_not_called()


def test_keep_instance_when_ip_lookup_succeeds(caplog):
    caplog.set_level(logging.INFO, logger="integration_testing")

    settings = mock.Mock()
    settings.KEEP_INSTANCE = True

    instance = mock.create_autospec(LXDInstance, instance=True)
    instance.execute_via_ssh = True

    type(instance).ip = mock.PropertyMock(return_value="192.0.2.10")

    cloud = mock.Mock()

    client = IntegrationInstance(
        cloud=cloud,
        instance=instance,
        settings=settings,
    )

    with client:
        pass

    cloud.reaper.reap.assert_not_called()
    assert "Keeping Instance, public ip: 192.0.2.10" in caplog.text
