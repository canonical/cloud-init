# This file is part of cloud-init. See LICENSE file for license information.

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


DISTRO_NAMES = ["ubuntu", "freebsd", "netbsd", "openbsd", "dragonflybsd"]


@pytest.mark.parametrize(
    "distro_name,expected_result",
    [
        ("ubuntu", True),
        ("freebsd", None),
        ("netbsd", None),
        ("openbsd", None),
        ("dragonflybsd", None),
    ],
)
def test_set_passwd_logs_security_event(
    distro_name, expected_result, mocker, caplog
):
    """set_passwd logs a security event and returns the distro result."""
    distro = get_distro(distro_name)
    operation = mocker.patch("cloudinit.subp.subp", return_value=("", ""))
    assert (
        distro.set_passwd("testuser", "$6$secret-hash", hashed=True)
        is expected_result
    )
    assert security_events(caplog) == [
        expected_event(
            "authn_password_change:cloud-init,testuser",
            "Password changed for user 'testuser'",
        )
    ]
    assert "$6$secret-hash" not in caplog.text
    operation.assert_called()


@pytest.mark.parametrize("distro_name", DISTRO_NAMES)
def test_chpasswd_logs_security_event_per_user(distro_name, mocker, caplog):
    """chpasswd logs one security event per user in the batch."""
    distro = get_distro(distro_name)
    operation = mocker.patch("cloudinit.subp.subp", return_value=("", ""))
    users = [("first", "$6$secret-hash"), ("second", "$6$other-hash")]
    assert distro.chpasswd(plist_in=users, hashed=True) is None
    assert security_events(caplog) == [
        expected_event(
            f"authn_password_change:cloud-init,{user}",
            f"Password changed for user '{user}'",
        )
        for user, _secret in users
    ]
    assert "$6$secret-hash" not in caplog.text
    assert "$6$other-hash" not in caplog.text
    operation.assert_called()


@pytest.mark.parametrize("distro_name", DISTRO_NAMES)
def test_set_passwd_failure_logs_no_security_event(
    distro_name, mocker, caplog
):
    """No security event is logged when a password change fails."""
    distro = get_distro(distro_name)
    mocker.patch(
        "cloudinit.subp.subp", side_effect=subp.ProcessExecutionError()
    )
    with pytest.raises(subp.ProcessExecutionError):
        distro.set_passwd("testuser", "$6$secret-hash", hashed=True)
    assert security_events(caplog) == []
    assert "$6$secret-hash" not in caplog.text


@pytest.mark.parametrize("distro_name", DISTRO_NAMES)
def test_chpasswd_failure_logs_no_security_event(distro_name, mocker, caplog):
    """No security event is logged when a batch password change fails."""
    distro = get_distro(distro_name)
    mocker.patch(
        "cloudinit.subp.subp", side_effect=subp.ProcessExecutionError()
    )
    with pytest.raises(subp.ProcessExecutionError):
        distro.chpasswd([("testuser", "$6$secret-hash")], hashed=True)
    assert security_events(caplog) == []
    assert "$6$secret-hash" not in caplog.text


@pytest.mark.parametrize(
    "call_args,call_kwargs",
    [
        (("testuser",), {"passwd": "plaintext-secret", "hashed": False}),
        (
            (),
            {
                "user": "testuser",
                "passwd": "plaintext-secret",
                "hashed": False,
            },
        ),
    ],
    ids=["positional", "keyword"],
)
def test_sec_log_password_changed_preserves_call_and_return(
    call_args, call_kwargs, caplog
):
    """The password decorator forwards calls and results, then logs."""
    calls = []

    def set_passwd(self, user, passwd, hashed):
        assert security_events(caplog) == []
        calls.append((self, user, passwd, hashed))
        return "result"

    wrapped = distros.sec_log_password_changed(set_passwd)
    assert wrapped(None, *call_args, **call_kwargs) == "result"
    assert calls == [(None, "testuser", "plaintext-secret", False)]
    assert security_events(caplog) == [
        expected_event(
            "authn_password_change:cloud-init,testuser",
            "Password changed for user 'testuser'",
        )
    ]


@pytest.mark.parametrize(
    "call_args,call_kwargs",
    [
        (
            ([("testuser", "plaintext-secret")],),
            {"hashed": False},
        ),
        (
            (),
            {
                "plist_in": [("testuser", "plaintext-secret")],
                "hashed": False,
            },
        ),
    ],
    ids=["positional", "keyword"],
)
def test_sec_log_password_changed_batch_preserves_call_and_return(
    call_args, call_kwargs, caplog
):
    """The batch decorator forwards calls and results, then logs."""
    calls = []

    def chpasswd(self, plist_in, hashed):
        assert security_events(caplog) == []
        calls.append((self, plist_in, hashed))
        return "result"

    wrapped = distros.sec_log_password_changed_batch(chpasswd)
    assert wrapped(None, *call_args, **call_kwargs) == "result"
    assert calls == [(None, [("testuser", "plaintext-secret")], False)]
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
    shutdown_command = distros.Distro.shutdown_command
    assert shutdown_command(mode=mode, delay=delay, message=message) == command
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
