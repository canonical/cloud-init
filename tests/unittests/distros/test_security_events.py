# This file is part of cloud-init. See LICENSE file for license information.

from typing import Dict, Union

import pytest

from cloudinit import distros, subp
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


@pytest.mark.parametrize(
    "distro_name", ["ubuntu", "freebsd", "netbsd", "openbsd", "dragonflybsd"]
)
@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("fails", [False, True])
def test_password_entry_points(distro_name, batch, fails, mocker, caplog):
    distro = get_distro(distro_name)
    operation = mocker.patch("cloudinit.subp.subp", return_value=("", ""))
    if fails:
        operation.side_effect = subp.ProcessExecutionError()
    users = [("first", "$6$secret-hash"), ("second", "$6$other-hash")]

    def change_passwords():
        if batch:
            return distro.chpasswd(plist_in=users, hashed=True)
        return distro.set_passwd(user="first", passwd=users[0][1], hashed=True)

    if fails:
        with pytest.raises(subp.ProcessExecutionError):
            change_passwords()
        assert security_events(caplog) == []
    else:
        result = change_passwords()
        assert result is (
            True if not batch and distro_name == "ubuntu" else None
        )
        assert security_events(caplog) == [
            expected_event(
                f"authn_password_change:cloud-init,{user}",
                f"Password changed for user '{user}'",
            )
            for user, _ in (users if batch else users[:1])
        ]
    operation.assert_called()


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("keyword", [False, True])
def test_password_decorators_preserve_calls_and_return(
    batch, keyword, mocker, caplog
):
    def perform_change(*args, **kwargs):
        assert security_events(caplog) == []
        return result_value

    result_value = object()
    operation = mocker.Mock(side_effect=perform_change)
    decorator = (
        distros.sec_log_password_changed_batch
        if batch
        else distros.sec_log_password_changed
    )
    wrapped = decorator(operation)
    argument = [("testuser", "plaintext-secret")] if batch else "testuser"
    kwargs: Dict[str, Union[bool, str]] = (
        {"hashed": False}
        if batch
        else {"hashed": False, "passwd": "plaintext-secret"}
    )
    if keyword:
        key = "plist_in" if batch else "user"
        result = wrapped(None, **{key: argument}, **kwargs)
    else:
        result = wrapped(None, argument, **kwargs)
    operation.assert_called_once_with(None, argument, **kwargs)
    assert result is result_value
    assert security_events(caplog) == [
        expected_event(
            "authn_password_change:cloud-init,testuser",
            "Password changed for user 'testuser'",
        )
    ]


def test_empty_password_batch(mocker, caplog):
    operation = mocker.Mock()
    distros.sec_log_password_changed_batch(operation)(None, [])
    operation.assert_called_once_with(None, [])
    assert security_events(caplog) == []


def test_bsd_batch_partial_failure(mocker, caplog):
    distro = get_distro("freebsd")
    mocker.patch(
        "cloudinit.subp.subp",
        side_effect=[("", ""), subp.ProcessExecutionError()],
    )
    with pytest.raises(subp.ProcessExecutionError):
        distro.chpasswd([("first", "secret"), ("second", "secret")], False)
    assert security_events(caplog) == [
        expected_event(
            "authn_password_change:cloud-init,first",
            "Password changed for user 'first'",
        )
    ]


@pytest.mark.parametrize(
    "mode,delay,message,event,description,command",
    [
        (
            "poweroff",
            5,
            "",
            "sys_shutdown",
            "System shutdown initiated",
            ["shutdown", "-P", "+5"],
        ),
        (
            "halt",
            "now",
            "",
            "sys_shutdown",
            "System shutdown initiated",
            ["shutdown", "-H", "now"],
        ),
        (
            "reboot",
            "now",
            "Restart FTW",
            "sys_restart",
            "System restart initiated: Restart FTW",
            ["shutdown", "-r", "now", "Restart FTW"],
        ),
    ],
)
def test_shutdown_entry_point(
    mode, delay, message, event, description, command, caplog
):
    assert (
        distros.Distro.shutdown_command(
            mode=mode, delay=delay, message=message
        )
        == command
    )
    assert security_events(caplog) == [
        expected_event(f"{event}:cloud-init", description)
    ]


def test_shutdown_logs_intent_before_command_validation(caplog):
    with pytest.raises(TypeError, match="power_state"):
        distros.Distro.shutdown_command(
            mode="reboot", delay="invalid", message=""
        )
    assert security_events(caplog) == [
        expected_event(
            "sys_restart:cloud-init",
            "System restart initiated",
        )
    ]
