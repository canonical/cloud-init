# This file is part of cloud-init. See LICENSE file for license information.

import pytest

from cloudinit import subp
from cloudinit.log import loggers
from tests.unittests.helpers import get_distro


@pytest.fixture(autouse=True)
def security_logging(mocker, caplog):
    mocker.patch("cloudinit.util.get_hostname", return_value="test-host")
    caplog.set_level(loggers.SECURITY)


def security_events(caplog):
    return [
        record.msg
        for record in caplog.records
        if record.levelno == loggers.SECURITY
    ]


def expected_event(event, description, **extra):
    return {
        "appid": "canonical.cloud-init",
        "type": "security",
        "event": event,
        "level": "INFO",
        "description": description,
        "hostname": "test-host",
        **extra,
    }


@pytest.mark.parametrize("method", ["add_user", "add_snap_user"])
@pytest.mark.parametrize("fails", [False, True])
def test_user_entry_points(method, fails, mocker, caplog):
    distro = get_distro("ubuntu")
    mocker.patch("cloudinit.distros.util.is_group", return_value=True)
    operation = mocker.patch.object(distro, "_add_user")
    if method == "add_snap_user":
        operation = mocker.patch(
            "cloudinit.distros.subp.subp", return_value=("", "")
        )
    if fails:
        operation.side_effect = subp.ProcessExecutionError()
        with pytest.raises(subp.ProcessExecutionError):
            getattr(distro, method)("testuser", groups=["adm"])
        assert security_events(caplog) == []
    else:
        getattr(distro, method)(
            name="testuser", groups=["adm"], sudo=True, doas=True
        )
        assert security_events(caplog) == [
            expected_event(
                "user_created:cloud-init,testuser,groups:adm,sudo,doas",
                "User 'testuser' was created in groups: adm,sudo,doas",
            )
        ]
    operation.assert_called_once()


@pytest.mark.parametrize("pre_existing", [False, True])
def test_create_user_only_logs_new_users(pre_existing, mocker, caplog):
    distro = get_distro("ubuntu")
    mocker.patch("cloudinit.distros.util.is_user", return_value=pre_existing)
    mocker.patch.object(distro, "_add_user")
    mocker.patch.object(distro, "lock_passwd")
    mocker.patch.object(
        distro, "_shadow_file_has_empty_user_password", return_value=False
    )
    distro.create_user("testuser", groups=[])
    expected = (
        []
        if pre_existing
        else [
            expected_event(
                "user_created:cloud-init,testuser",
                "User 'testuser' was created",
            )
        ]
    )
    assert security_events(caplog) == expected
