# This file is part of cloud-init. See LICENSE file for license information.

import sys

import pytest

from cloudinit import distros, helpers
from cloudinit.config import cc_power_state_change as psc
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import mock, skipUnlessJsonSchema


@pytest.fixture
def dist():
    cls = distros.fetch("ubuntu")
    paths = helpers.Paths({})
    return cls("ubuntu", {}, paths)


class TestLoadPowerState:

    def test_no_config(self, dist):
        # completely empty config should mean do nothing
        (cmd, _timeout, _condition) = psc.load_power_state({}, dist)
        assert cmd is None

    def test_irrelevant_config(self, dist):
        # no power_state field in config should return None for cmd
        (cmd, _timeout, _condition) = psc.load_power_state(
            {"foo": "bar"}, dist
        )
        assert cmd is None

    def test_invalid_mode(self, dist):

        cfg = {"power_state": {"mode": "gibberish"}}
        with pytest.raises(TypeError):
            psc.load_power_state(cfg, dist)

        cfg = {"power_state": {"mode": ""}}
        with pytest.raises(TypeError):
            psc.load_power_state(cfg, dist)

    def test_empty_mode(self, dist):
        cfg = {"power_state": {"message": "goodbye"}}
        with pytest.raises(TypeError):
            psc.load_power_state(cfg, dist)

    def test_valid_modes(self, dist):
        cfg: dict = {"power_state": {}}
        for mode in ("halt", "poweroff", "reboot"):
            cfg["power_state"]["mode"] = mode
            check_lps_ret(psc.load_power_state(cfg, dist), mode=mode)

    def test_invalid_delay(self, dist):
        cfg = {"power_state": {"mode": "poweroff", "delay": "goodbye"}}
        with pytest.raises(TypeError):
            psc.load_power_state(cfg, dist)

    def test_valid_delay(self, dist):
        cfg = {"power_state": {"mode": "poweroff", "delay": ""}}
        for delay in ("now", "+1", "+30"):
            cfg["power_state"]["delay"] = delay
            check_lps_ret(psc.load_power_state(cfg, dist))

    def test_message_present(self, dist):
        cfg = {"power_state": {"mode": "poweroff", "message": "GOODBYE"}}
        ret = psc.load_power_state(cfg, dist)
        check_lps_ret(ret)
        assert cfg["power_state"]["message"] in ret[0]

    def test_no_message(self, dist):
        # if message is not present, then no argument should be passed for it
        cfg = {"power_state": {"mode": "poweroff"}}
        (cmd, _timeout, _condition) = psc.load_power_state(cfg, dist)
        assert "" not in cmd
        check_lps_ret(psc.load_power_state(cfg, dist))
        assert len(cmd) == 3

    def test_condition_null_raises(self, dist):
        cfg = {"power_state": {"mode": "poweroff", "condition": None}}
        with pytest.raises(TypeError):
            psc.load_power_state(cfg, dist)

    def test_condition_default_is_true(self, dist):
        cfg = {"power_state": {"mode": "poweroff"}}
        _cmd, _timeout, cond = psc.load_power_state(cfg, dist)
        assert cond is True

    def test_freebsd_poweroff_uses_lowercase_p(self):
        with mock.patch(
            "cloudinit.distros.networking.subp.subp",
            return_value=("", None),
        ):
            cls = distros.fetch("freebsd")
            paths = helpers.Paths({})
            freebsd = cls("freebsd", {}, paths)
            cfg = {"power_state": {"mode": "poweroff"}}
            ret = psc.load_power_state(cfg, freebsd)
            assert "-p" in ret[0]

    def test_alpine_delay(self):
        # alpine takes delay in seconds.
        cls = distros.fetch("alpine")
        paths = helpers.Paths({})
        alpine = cls("alpine", {}, paths)
        cfg = {"power_state": {"mode": "poweroff", "delay": ""}}
        for delay, value in (("now", 0), ("+1", 60), ("+30", 1800)):
            cfg["power_state"]["delay"] = delay
            ret = psc.load_power_state(cfg, alpine)
            assert ret[0][1] == "-d"
            assert ret[0][2] == str(value)


class TestCheckCondition:
    def cmd_with_exit(self, rc):
        return [sys.executable, "-c", "import sys; sys.exit(%s)" % rc]

    def test_true_is_true(self):
        assert psc.check_condition(True) is True

    def test_false_is_false(self):
        assert psc.check_condition(False) is False

    def test_cmd_exit_zero_true(self):
        assert psc.check_condition(self.cmd_with_exit(0)) is True

    def test_cmd_exit_one_false(self):
        assert psc.check_condition(self.cmd_with_exit(1)) is False

    @mock.patch("cloudinit.config.cc_power_state_change.LOG")
    def test_cmd_exit_nonzero_warns(self, mocklog):
        assert psc.check_condition(self.cmd_with_exit(2)) is False
        assert mocklog.warning.call_count == 1


def check_lps_ret(psc_return, mode=None):
    if len(psc_return) != 3:
        raise TypeError("length returned = %d" % len(psc_return))

    errs = []
    cmd = psc_return[0]
    timeout = psc_return[1]
    condition = psc_return[2]

    if "shutdown" not in psc_return[0][0]:
        errs.append("string 'shutdown' not in cmd")

    if condition is None:
        errs.append("condition was not returned")

    if mode is not None:
        opt = {"halt": "-H", "poweroff": "-P", "reboot": "-r"}[mode]
        if opt not in psc_return[0]:
            errs.append("opt '%s' not in cmd: %s" % (opt, cmd))

    if len(cmd) != 3 and len(cmd) != 4:
        errs.append("Invalid command length: %s" % len(cmd))

    try:
        float(timeout)
    except Exception:
        errs.append("timeout failed convert to float")

    if len(errs):
        lines = ["Errors in result: %s" % str(psc_return)] + errs
        raise RuntimeError("\n".join(lines))


class TestPowerStateChangeSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Invalid mode
            (
                {"power_state": {"mode": "test"}},
                r"'test' is not one of \['poweroff', 'reboot', 'halt'\]",
            ),
            # Delay can be a number, a +number, or "now"
            (
                {"power_state": {"mode": "halt", "delay": "5"}},
                (
                    "Cloud config schema deprecations: "
                    "power_state.delay:  Changed in version 22.3. Use "
                    "of type string for this value is deprecated. Use "
                    "``now`` or integer type."
                ),
            ),
            ({"power_state": {"mode": "halt", "delay": "now"}}, None),
            (
                {"power_state": {"mode": "halt", "delay": "+5"}},
                (
                    "Cloud config schema deprecations: "
                    "power_state.delay:  Changed in version 22.3. Use "
                    "of type string for this value is deprecated. Use "
                    "``now`` or integer type."
                ),
            ),
            ({"power_state": {"mode": "halt", "delay": "+"}}, ""),
            ({"power_state": {"mode": "halt", "delay": "++5"}}, ""),
            ({"power_state": {"mode": "halt", "delay": "-5"}}, ""),
            ({"power_state": {"mode": "halt", "delay": "test"}}, ""),
            # Condition
            ({"power_state": {"mode": "halt", "condition": False}}, None),
            ({"power_state": {"mode": "halt", "condition": "ls /tmp"}}, None),
            (
                {"power_state": {"mode": "halt", "condition": ["ls", "/tmp"]}},
                None,
            ),
            ({"power_state": {"mode": "halt", "condition": 5}}, ""),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
