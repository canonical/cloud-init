from cloudinit.config import cc_power_state_change as psc

from .. import helpers as t_help


class TestLoadPowerState(t_help.TestCase):
    def setUp(self):
        super(self.__class__, self).setUp()

    def test_no_config(self):
        # completely empty config should mean do nothing
        (cmd, _timeout) = psc.load_power_state({})
        self.assertEqual(cmd, None)

    def test_irrelevant_config(self):
        # no power_state field in config should return None for cmd
        (cmd, _timeout) = psc.load_power_state({'foo': 'bar'})
        self.assertEqual(cmd, None)

    def test_invalid_mode(self):
        cfg = {'power_state': {'mode': 'gibberish'}}
        self.assertRaises(TypeError, psc.load_power_state, cfg)

        cfg = {'power_state': {'mode': ''}}
        self.assertRaises(TypeError, psc.load_power_state, cfg)

    def test_empty_mode(self):
        cfg = {'power_state': {'message': 'goodbye'}}
        self.assertRaises(TypeError, psc.load_power_state, cfg)

    def test_valid_modes(self):
        cfg = {'power_state': {}}
        for mode in ('halt', 'poweroff', 'reboot'):
            cfg['power_state']['mode'] = mode
            check_lps_ret(psc.load_power_state(cfg), mode=mode)

    def test_invalid_delay(self):
        cfg = {'power_state': {'mode': 'poweroff', 'delay': 'goodbye'}}
        self.assertRaises(TypeError, psc.load_power_state, cfg)

    def test_valid_delay(self):
        cfg = {'power_state': {'mode': 'poweroff', 'delay': ''}}
        for delay in ("now", "+1", "+30"):
            cfg['power_state']['delay'] = delay
            check_lps_ret(psc.load_power_state(cfg))

    def test_message_present(self):
        cfg = {'power_state': {'mode': 'poweroff', 'message': 'GOODBYE'}}
        ret = psc.load_power_state(cfg)
        check_lps_ret(psc.load_power_state(cfg))
        self.assertIn(cfg['power_state']['message'], ret[0])

    def test_no_message(self):
        # if message is not present, then no argument should be passed for it
        cfg = {'power_state': {'mode': 'poweroff'}}
        (cmd, _timeout) = psc.load_power_state(cfg)
        self.assertNotIn("", cmd)
        check_lps_ret(psc.load_power_state(cfg))
        self.assertTrue(len(cmd) == 3)


def check_lps_ret(psc_return, mode=None):
    if len(psc_return) != 2:
        raise TypeError("length returned = %d" % len(psc_return))

    errs = []
    cmd = psc_return[0]
    timeout = psc_return[1]

    if 'shutdown' not in psc_return[0][0]:
        errs.append("string 'shutdown' not in cmd")

    if mode is not None:
        opt = {'halt': '-H', 'poweroff': '-P', 'reboot': '-r'}[mode]
        if opt not in psc_return[0]:
            errs.append("opt '%s' not in cmd: %s" % (opt, cmd))

    if len(cmd) != 3 and len(cmd) != 4:
        errs.append("Invalid command length: %s" % len(cmd))

    try:
        float(timeout)
    except:
        errs.append("timeout failed convert to float")

    if len(errs):
        lines = ["Errors in result: %s" % str(psc_return)] + errs
        raise Exception('\n'.join(lines))
