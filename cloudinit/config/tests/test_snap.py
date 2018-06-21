# This file is part of cloud-init. See LICENSE file for license information.

import re
from six import StringIO

from cloudinit.config.cc_snap import (
    ASSERTIONS_FILE, add_assertions, handle, maybe_install_squashfuse,
    run_commands, schema)
from cloudinit.config.schema import validate_cloudconfig_schema
from cloudinit import util
from cloudinit.tests.helpers import (
    CiTestCase, SchemaTestCaseMixin, mock, wrap_and_call, skipUnlessJsonSchema)


SYSTEM_USER_ASSERTION = """\
type: system-user
authority-id: LqvZQdfyfGlYvtep4W6Oj6pFXP9t1Ksp
brand-id: LqvZQdfyfGlYvtep4W6Oj6pFXP9t1Ksp
email: foo@bar.com
password: $6$E5YiAuMIPAwX58jG$miomhVNui/vf7f/3ctB/f0RWSKFxG0YXzrJ9rtJ1ikvzt
series:
- 16
since: 2016-09-10T16:34:00+03:00
until: 2017-11-10T16:34:00+03:00
username: baz
sign-key-sha3-384: RuVvnp4n52GilycjfbbTCI3_L8Y6QlIE75wxMc0KzGV3AUQqVd9GuXoj

AcLBXAQAAQoABgUCV/UU1wAKCRBKnlMoJQLkZVeLD/9/+hIeVywtzsDA3oxl+P+u9D13y9s6svP
Jd6Wnf4FTw6sq1GjBE4ZA7lrwSaRCUJ9Vcsvf2q9OGPY7mOb2TBxaDe0PbUMjrSrqllSSQwhpNI
zG+NxkkKuxsUmLzFa+k9m6cyojNbw5LFhQZBQCGlr3JYqC0tIREq/UsZxj+90TUC87lDJwkU8GF
s4CR+rejZj4itIcDcVxCSnJH6hv6j2JrJskJmvObqTnoOlcab+JXdamXqbldSP3UIhWoyVjqzkj
+to7mXgx+cCUA9+ngNCcfUG+1huGGTWXPCYkZ78HvErcRlIdeo4d3xwtz1cl/w3vYnq9og1XwsP
Yfetr3boig2qs1Y+j/LpsfYBYncgWjeDfAB9ZZaqQz/oc8n87tIPZDJHrusTlBfop8CqcM4xsKS
d+wnEY8e/F24mdSOYmS1vQCIDiRU3MKb6x138Ud6oHXFlRBbBJqMMctPqWDunWzb5QJ7YR0I39q
BrnEqv5NE0G7w6HOJ1LSPG5Hae3P4T2ea+ATgkb03RPr3KnXnzXg4TtBbW1nytdlgoNc/BafE1H
f3NThcq9gwX4xWZ2PAWnqVPYdDMyCtzW3Ck+o6sIzx+dh4gDLPHIi/6TPe/pUuMop9CBpWwez7V
v1z+1+URx6Xlq3Jq18y5pZ6fY3IDJ6km2nQPMzcm4Q=="""

ACCOUNT_ASSERTION = """\
type: account-key
authority-id: canonical
revision: 2
public-key-sha3-384: BWDEoaqyr25nF5SNCvEv2v7QnM9QsfCc0PBMYD_i2NGSQ32EF2d4D0
account-id: canonical
name: store
since: 2016-04-01T00:00:00.0Z
body-length: 717
sign-key-sha3-384: -CvQKAwRQ5h3Ffn10FILJoEZUXOv6km9FwA80-Rcj-f-6jadQ89VRswH

AcbBTQRWhcGAARAA0KKYYQWuHOrsFVi4p4l7ZzSvX7kLgJFFeFgOkzdWKBTHEnsMKjl5mefFe9j
qe8NlmJdfY7BenP7XeBtwKp700H/t9lLrZbpTNAPHXYxEWFJp5bPqIcJYBZ+29oLVLN1Tc5X482
vCiDqL8+pPYqBrK2fNlyPlNNSum9wI70rDDL4r6FVvr+osTnGejibdV8JphWX+lrSQDnRSdM8KJ
UM43vTgLGTi9W54oRhsA2OFexRfRksTrnqGoonCjqX5wO3OFSaMDzMsO2MJ/hPfLgDqw53qjzuK
Iec9OL3k5basvu2cj5u9tKwVFDsCKK2GbKUsWWpx2KTpOifmhmiAbzkTHbH9KaoMS7p0kJwhTQG
o9aJ9VMTWHJc/NCBx7eu451u6d46sBPCXS/OMUh2766fQmoRtO1OwCTxsRKG2kkjbMn54UdFULl
VfzvyghMNRKIezsEkmM8wueTqGUGZWa6CEZqZKwhe/PROxOPYzqtDH18XZknbU1n5lNb7vNfem9
2ai+3+JyFnW9UhfvpVF7gzAgdyCqNli4C6BIN43uwoS8HkykocZS/+Gv52aUQ/NZ8BKOHLw+7an
Q0o8W9ltSLZbEMxFIPSN0stiZlkXAp6DLyvh1Y4wXSynDjUondTpej2fSvSlCz/W5v5V7qA4nIc
vUvV7RjVzv17ut0AEQEAAQ==

AcLDXAQAAQoABgUCV83k9QAKCRDUpVvql9g3IBT8IACKZ7XpiBZ3W4lqbPssY6On81WmxQLtvsM
WTp6zZpl/wWOSt2vMNUk9pvcmrNq1jG9CuhDfWFLGXEjcrrmVkN3YuCOajMSPFCGrxsIBLSRt/b
nrKykdLAAzMfG8rP1d82bjFFiIieE+urQ0Kcv09Jtdvavq3JT1Tek5mFyyfhHNlQEKOzWqmRWiL
3c3VOZUs1ZD8TSlnuq/x+5T0X0YtOyGjSlVxk7UybbyMNd6MZfNaMpIG4x+mxD3KHFtBAC7O6kL
eX3i6j5nCY5UABfA3DZEAkWP4zlmdBEOvZ9t293NaDdOpzsUHRkoi0Zez/9BHQ/kwx/uNc2WqrY
inCmu16JGNeXqsyinnLl7Ghn2RwhvDMlLxF6RTx8xdx1yk6p3PBTwhZMUvuZGjUtN/AG8BmVJQ1
rsGSRkkSywvnhVJRB2sudnrMBmNS2goJbzSbmJnOlBrd2WsV0T9SgNMWZBiov3LvU4o2SmAb6b+
rYwh8H5QHcuuYJuxDjFhPswIp6Wes5T6hUicf3SWtObcDS4HSkVS4ImBjjX9YgCuFy7QdnooOWE
aPvkRw3XCVeYq0K6w9GRsk1YFErD4XmXXZjDYY650MX9v42Sz5MmphHV8jdIY5ssbadwFSe2rCQ
6UX08zy7RsIb19hTndE6ncvSNDChUR9eEnCm73eYaWTWTnq1cxdVP/s52r8uss++OYOkPWqh5nO
haRn7INjH/yZX4qXjNXlTjo0PnHH0q08vNKDwLhxS+D9du+70FeacXFyLIbcWllSbJ7DmbumGpF
yYbtj3FDDPzachFQdIG3lSt+cSUGeyfSs6wVtc3cIPka/2Urx7RprfmoWSI6+a5NcLdj0u2z8O9
HxeIgxDpg/3gT8ZIuFKePMcLDM19Fh/p0ysCsX+84B9chNWtsMSmIaE57V+959MVtsLu7SLb9gi
skrju0pQCwsu2wHMLTNd1f3PTHmrr49hxetTus07HSQUApMtAGKzQilF5zqFjbyaTd4xgQbd+PK
CjFyzQTDOcUhXpuUGt/IzlqiFfsCsmbj2K4KdSNYMlqIgZ3Azu8KvZLIhsyN7v5vNIZSPfEbjde
ClU9r0VRiJmtYBUjcSghD9LWn+yRLwOxhfQVjm0cBwIt5R/yPF/qC76yIVuWUtM5Y2/zJR1J8OF
qWchvlImHtvDzS9FQeLyzJAOjvZ2CnWp2gILgUz0WQdOk1Dq8ax7KS9BQ42zxw9EZAEPw3PEFqR
IQsRTONp+iVS8YxSmoYZjDlCgRMWUmawez/Fv5b9Fb/XkO5Eq4e+KfrpUujXItaipb+tV8h5v3t
oG3Ie3WOHrVjCLXIdYslpL1O4nadqR6Xv58pHj6k"""


class FakeCloud(object):
    def __init__(self, distro):
        self.distro = distro


class TestAddAssertions(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestAddAssertions, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch('cloudinit.config.cc_snap.util.subp')
    def test_add_assertions_on_empty_list(self, m_subp):
        """When provided with an empty list, add_assertions does nothing."""
        add_assertions([])
        self.assertEqual('', self.logs.getvalue())
        m_subp.assert_not_called()

    def test_add_assertions_on_non_list_or_dict(self):
        """When provided an invalid type, add_assertions raises an error."""
        with self.assertRaises(TypeError) as context_manager:
            add_assertions(assertions="I'm Not Valid")
        self.assertEqual(
            "assertion parameter was not a list or dict: I'm Not Valid",
            str(context_manager.exception))

    @mock.patch('cloudinit.config.cc_snap.util.subp')
    def test_add_assertions_adds_assertions_as_list(self, m_subp):
        """When provided with a list, add_assertions adds all assertions."""
        self.assertEqual(
            ASSERTIONS_FILE, '/var/lib/cloud/instance/snapd.assertions')
        assert_file = self.tmp_path('snapd.assertions', dir=self.tmp)
        assertions = [SYSTEM_USER_ASSERTION, ACCOUNT_ASSERTION]
        wrap_and_call(
            'cloudinit.config.cc_snap',
            {'ASSERTIONS_FILE': {'new': assert_file}},
            add_assertions, assertions)
        self.assertIn(
            'Importing user-provided snap assertions', self.logs.getvalue())
        self.assertIn(
            'sertions', self.logs.getvalue())
        self.assertEqual(
            [mock.call(['snap', 'ack', assert_file], capture=True)],
            m_subp.call_args_list)
        compare_file = self.tmp_path('comparison', dir=self.tmp)
        util.write_file(compare_file, '\n'.join(assertions).encode('utf-8'))
        self.assertEqual(
            util.load_file(compare_file), util.load_file(assert_file))

    @mock.patch('cloudinit.config.cc_snap.util.subp')
    def test_add_assertions_adds_assertions_as_dict(self, m_subp):
        """When provided with a dict, add_assertions adds all assertions."""
        self.assertEqual(
            ASSERTIONS_FILE, '/var/lib/cloud/instance/snapd.assertions')
        assert_file = self.tmp_path('snapd.assertions', dir=self.tmp)
        assertions = {'00': SYSTEM_USER_ASSERTION, '01': ACCOUNT_ASSERTION}
        wrap_and_call(
            'cloudinit.config.cc_snap',
            {'ASSERTIONS_FILE': {'new': assert_file}},
            add_assertions, assertions)
        self.assertIn(
            'Importing user-provided snap assertions', self.logs.getvalue())
        self.assertIn(
            "DEBUG: Snap acking: ['type: system-user', 'authority-id: Lqv",
            self.logs.getvalue())
        self.assertIn(
            "DEBUG: Snap acking: ['type: account-key', 'authority-id: canonic",
            self.logs.getvalue())
        self.assertEqual(
            [mock.call(['snap', 'ack', assert_file], capture=True)],
            m_subp.call_args_list)
        compare_file = self.tmp_path('comparison', dir=self.tmp)
        combined = '\n'.join(assertions.values())
        util.write_file(compare_file, combined.encode('utf-8'))
        self.assertEqual(
            util.load_file(compare_file), util.load_file(assert_file))


class TestRunCommands(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestRunCommands, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch('cloudinit.config.cc_snap.util.subp')
    def test_run_commands_on_empty_list(self, m_subp):
        """When provided with an empty list, run_commands does nothing."""
        run_commands([])
        self.assertEqual('', self.logs.getvalue())
        m_subp.assert_not_called()

    def test_run_commands_on_non_list_or_dict(self):
        """When provided an invalid type, run_commands raises an error."""
        with self.assertRaises(TypeError) as context_manager:
            run_commands(commands="I'm Not Valid")
        self.assertEqual(
            "commands parameter was not a list or dict: I'm Not Valid",
            str(context_manager.exception))

    def test_run_command_logs_commands_and_exit_codes_to_stderr(self):
        """All exit codes are logged to stderr."""
        outfile = self.tmp_path('output.log', dir=self.tmp)

        cmd1 = 'echo "HI" >> %s' % outfile
        cmd2 = 'bogus command'
        cmd3 = 'echo "MOM" >> %s' % outfile
        commands = [cmd1, cmd2, cmd3]

        mock_path = 'cloudinit.config.cc_snap.sys.stderr'
        with mock.patch(mock_path, new_callable=StringIO) as m_stderr:
            with self.assertRaises(RuntimeError) as context_manager:
                run_commands(commands=commands)

        self.assertIsNotNone(
            re.search(r'bogus: (command )?not found',
                      str(context_manager.exception)),
            msg='Expected bogus command not found')
        expected_stderr_log = '\n'.join([
            'Begin run command: {cmd}'.format(cmd=cmd1),
            'End run command: exit(0)',
            'Begin run command: {cmd}'.format(cmd=cmd2),
            'ERROR: End run command: exit(127)',
            'Begin run command: {cmd}'.format(cmd=cmd3),
            'End run command: exit(0)\n'])
        self.assertEqual(expected_stderr_log, m_stderr.getvalue())

    def test_run_command_as_lists(self):
        """When commands are specified as a list, run them in order."""
        outfile = self.tmp_path('output.log', dir=self.tmp)

        cmd1 = 'echo "HI" >> %s' % outfile
        cmd2 = 'echo "MOM" >> %s' % outfile
        commands = [cmd1, cmd2]
        mock_path = 'cloudinit.config.cc_snap.sys.stderr'
        with mock.patch(mock_path, new_callable=StringIO):
            run_commands(commands=commands)

        self.assertIn(
            'DEBUG: Running user-provided snap commands',
            self.logs.getvalue())
        self.assertEqual('HI\nMOM\n', util.load_file(outfile))
        self.assertIn(
            'WARNING: Non-snap commands in snap config:', self.logs.getvalue())

    def test_run_command_dict_sorted_as_command_script(self):
        """When commands are a dict, sort them and run."""
        outfile = self.tmp_path('output.log', dir=self.tmp)
        cmd1 = 'echo "HI" >> %s' % outfile
        cmd2 = 'echo "MOM" >> %s' % outfile
        commands = {'02': cmd1, '01': cmd2}
        mock_path = 'cloudinit.config.cc_snap.sys.stderr'
        with mock.patch(mock_path, new_callable=StringIO):
            run_commands(commands=commands)

        expected_messages = [
            'DEBUG: Running user-provided snap commands']
        for message in expected_messages:
            self.assertIn(message, self.logs.getvalue())
        self.assertEqual('MOM\nHI\n', util.load_file(outfile))


@skipUnlessJsonSchema()
class TestSchema(CiTestCase, SchemaTestCaseMixin):

    with_logs = True
    schema = schema

    def test_schema_warns_on_snap_not_as_dict(self):
        """If the snap configuration is not a dict, emit a warning."""
        validate_cloudconfig_schema({'snap': 'wrong type'}, schema)
        self.assertEqual(
            "WARNING: Invalid config:\nsnap: 'wrong type' is not of type"
            " 'object'\n",
            self.logs.getvalue())

    @mock.patch('cloudinit.config.cc_snap.run_commands')
    def test_schema_disallows_unknown_keys(self, _):
        """Unknown keys in the snap configuration emit warnings."""
        validate_cloudconfig_schema(
            {'snap': {'commands': ['ls'], 'invalid-key': ''}}, schema)
        self.assertIn(
            'WARNING: Invalid config:\nsnap: Additional properties are not'
            " allowed ('invalid-key' was unexpected)",
            self.logs.getvalue())

    def test_warn_schema_requires_either_commands_or_assertions(self):
        """Warn when snap configuration lacks both commands and assertions."""
        validate_cloudconfig_schema(
            {'snap': {}}, schema)
        self.assertIn(
            'WARNING: Invalid config:\nsnap: {} does not have enough'
            ' properties',
            self.logs.getvalue())

    @mock.patch('cloudinit.config.cc_snap.run_commands')
    def test_warn_schema_commands_is_not_list_or_dict(self, _):
        """Warn when snap:commands config is not a list or dict."""
        validate_cloudconfig_schema(
            {'snap': {'commands': 'broken'}}, schema)
        self.assertEqual(
            "WARNING: Invalid config:\nsnap.commands: 'broken' is not of type"
            " 'object', 'array'\n",
            self.logs.getvalue())

    @mock.patch('cloudinit.config.cc_snap.run_commands')
    def test_warn_schema_when_commands_is_empty(self, _):
        """Emit warnings when snap:commands is an empty list or dict."""
        validate_cloudconfig_schema(
            {'snap': {'commands': []}}, schema)
        validate_cloudconfig_schema(
            {'snap': {'commands': {}}}, schema)
        self.assertEqual(
            "WARNING: Invalid config:\nsnap.commands: [] is too short\n"
            "WARNING: Invalid config:\nsnap.commands: {} does not have enough"
            " properties\n",
            self.logs.getvalue())

    @mock.patch('cloudinit.config.cc_snap.run_commands')
    def test_schema_when_commands_are_list_or_dict(self, _):
        """No warnings when snap:commands are either a list or dict."""
        validate_cloudconfig_schema(
            {'snap': {'commands': ['valid']}}, schema)
        validate_cloudconfig_schema(
            {'snap': {'commands': {'01': 'also valid'}}}, schema)
        self.assertEqual('', self.logs.getvalue())

    @mock.patch('cloudinit.config.cc_snap.add_assertions')
    def test_warn_schema_assertions_is_not_list_or_dict(self, _):
        """Warn when snap:assertions config is not a list or dict."""
        validate_cloudconfig_schema(
            {'snap': {'assertions': 'broken'}}, schema)
        self.assertEqual(
            "WARNING: Invalid config:\nsnap.assertions: 'broken' is not of"
            " type 'object', 'array'\n",
            self.logs.getvalue())

    @mock.patch('cloudinit.config.cc_snap.add_assertions')
    def test_warn_schema_when_assertions_is_empty(self, _):
        """Emit warnings when snap:assertions is an empty list or dict."""
        validate_cloudconfig_schema(
            {'snap': {'assertions': []}}, schema)
        validate_cloudconfig_schema(
            {'snap': {'assertions': {}}}, schema)
        self.assertEqual(
            "WARNING: Invalid config:\nsnap.assertions: [] is too short\n"
            "WARNING: Invalid config:\nsnap.assertions: {} does not have"
            " enough properties\n",
            self.logs.getvalue())

    @mock.patch('cloudinit.config.cc_snap.add_assertions')
    def test_schema_when_assertions_are_list_or_dict(self, _):
        """No warnings when snap:assertions are a list or dict."""
        validate_cloudconfig_schema(
            {'snap': {'assertions': ['valid']}}, schema)
        validate_cloudconfig_schema(
            {'snap': {'assertions': {'01': 'also valid'}}}, schema)
        self.assertEqual('', self.logs.getvalue())

    def test_duplicates_are_fine_array_array(self):
        """Duplicated commands array/array entries are allowed."""
        self.assertSchemaValid(
            {'commands': [["echo", "bye"], ["echo" "bye"]]},
            "command entries can be duplicate.")

    def test_duplicates_are_fine_array_string(self):
        """Duplicated commands array/string entries are allowed."""
        self.assertSchemaValid(
            {'commands': ["echo bye", "echo bye"]},
            "command entries can be duplicate.")

    def test_duplicates_are_fine_dict_array(self):
        """Duplicated commands dict/array entries are allowed."""
        self.assertSchemaValid(
            {'commands': {'00': ["echo", "bye"], '01': ["echo", "bye"]}},
            "command entries can be duplicate.")

    def test_duplicates_are_fine_dict_string(self):
        """Duplicated commands dict/string entries are allowed."""
        self.assertSchemaValid(
            {'commands': {'00': "echo bye", '01': "echo bye"}},
            "command entries can be duplicate.")


class TestHandle(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestHandle, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch('cloudinit.config.cc_snap.run_commands')
    @mock.patch('cloudinit.config.cc_snap.add_assertions')
    @mock.patch('cloudinit.config.cc_snap.validate_cloudconfig_schema')
    def test_handle_no_config(self, m_schema, m_add, m_run):
        """When no snap-related configuration is provided, nothing happens."""
        cfg = {}
        handle('snap', cfg=cfg, cloud=None, log=self.logger, args=None)
        self.assertIn(
            "DEBUG: Skipping module named snap, no 'snap' key in config",
            self.logs.getvalue())
        m_schema.assert_not_called()
        m_add.assert_not_called()
        m_run.assert_not_called()

    @mock.patch('cloudinit.config.cc_snap.run_commands')
    @mock.patch('cloudinit.config.cc_snap.add_assertions')
    @mock.patch('cloudinit.config.cc_snap.maybe_install_squashfuse')
    def test_handle_skips_squashfuse_when_unconfigured(self, m_squash, m_add,
                                                       m_run):
        """When squashfuse_in_container is unset, don't attempt to install."""
        handle(
            'snap', cfg={'snap': {}}, cloud=None, log=self.logger, args=None)
        handle(
            'snap', cfg={'snap': {'squashfuse_in_container': None}},
            cloud=None, log=self.logger, args=None)
        handle(
            'snap', cfg={'snap': {'squashfuse_in_container': False}},
            cloud=None, log=self.logger, args=None)
        self.assertEqual([], m_squash.call_args_list)  # No calls
        # snap configuration missing assertions and commands will default to []
        self.assertIn(mock.call([]), m_add.call_args_list)
        self.assertIn(mock.call([]), m_run.call_args_list)

    @mock.patch('cloudinit.config.cc_snap.maybe_install_squashfuse')
    def test_handle_tries_to_install_squashfuse(self, m_squash):
        """If squashfuse_in_container is True, try installing squashfuse."""
        cfg = {'snap': {'squashfuse_in_container': True}}
        mycloud = FakeCloud(None)
        handle('snap', cfg=cfg, cloud=mycloud, log=self.logger, args=None)
        self.assertEqual(
            [mock.call(mycloud)], m_squash.call_args_list)

    def test_handle_runs_commands_provided(self):
        """If commands are specified as a list, run them."""
        outfile = self.tmp_path('output.log', dir=self.tmp)

        cfg = {
            'snap': {'commands': ['echo "HI" >> %s' % outfile,
                                  'echo "MOM" >> %s' % outfile]}}
        mock_path = 'cloudinit.config.cc_snap.sys.stderr'
        with mock.patch(mock_path, new_callable=StringIO):
            handle('snap', cfg=cfg, cloud=None, log=self.logger, args=None)
        self.assertEqual('HI\nMOM\n', util.load_file(outfile))

    @mock.patch('cloudinit.config.cc_snap.util.subp')
    def test_handle_adds_assertions(self, m_subp):
        """Any configured snap assertions are provided to add_assertions."""
        assert_file = self.tmp_path('snapd.assertions', dir=self.tmp)
        compare_file = self.tmp_path('comparison', dir=self.tmp)
        cfg = {
            'snap': {'assertions': [SYSTEM_USER_ASSERTION, ACCOUNT_ASSERTION]}}
        wrap_and_call(
            'cloudinit.config.cc_snap',
            {'ASSERTIONS_FILE': {'new': assert_file}},
            handle, 'snap', cfg=cfg, cloud=None, log=self.logger, args=None)
        content = '\n'.join(cfg['snap']['assertions'])
        util.write_file(compare_file, content.encode('utf-8'))
        self.assertEqual(
            util.load_file(compare_file), util.load_file(assert_file))

    @mock.patch('cloudinit.config.cc_snap.util.subp')
    @skipUnlessJsonSchema()
    def test_handle_validates_schema(self, m_subp):
        """Any provided configuration is runs validate_cloudconfig_schema."""
        assert_file = self.tmp_path('snapd.assertions', dir=self.tmp)
        cfg = {'snap': {'invalid': ''}}  # Generates schema warning
        wrap_and_call(
            'cloudinit.config.cc_snap',
            {'ASSERTIONS_FILE': {'new': assert_file}},
            handle, 'snap', cfg=cfg, cloud=None, log=self.logger, args=None)
        self.assertEqual(
            "WARNING: Invalid config:\nsnap: Additional properties are not"
            " allowed ('invalid' was unexpected)\n",
            self.logs.getvalue())


class TestMaybeInstallSquashFuse(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestMaybeInstallSquashFuse, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch('cloudinit.config.cc_snap.util.is_container')
    def test_maybe_install_squashfuse_skips_non_containers(self, m_container):
        """maybe_install_squashfuse does nothing when not on a container."""
        m_container.return_value = False
        maybe_install_squashfuse(cloud=FakeCloud(None))
        self.assertEqual([mock.call()], m_container.call_args_list)
        self.assertEqual('', self.logs.getvalue())

    @mock.patch('cloudinit.config.cc_snap.util.is_container')
    def test_maybe_install_squashfuse_raises_install_errors(self, m_container):
        """maybe_install_squashfuse logs and raises package install errors."""
        m_container.return_value = True
        distro = mock.MagicMock()
        distro.update_package_sources.side_effect = RuntimeError(
            'Some apt error')
        with self.assertRaises(RuntimeError) as context_manager:
            maybe_install_squashfuse(cloud=FakeCloud(distro))
        self.assertEqual('Some apt error', str(context_manager.exception))
        self.assertIn('Package update failed\nTraceback', self.logs.getvalue())

    @mock.patch('cloudinit.config.cc_snap.util.is_container')
    def test_maybe_install_squashfuse_raises_update_errors(self, m_container):
        """maybe_install_squashfuse logs and raises package update errors."""
        m_container.return_value = True
        distro = mock.MagicMock()
        distro.update_package_sources.side_effect = RuntimeError(
            'Some apt error')
        with self.assertRaises(RuntimeError) as context_manager:
            maybe_install_squashfuse(cloud=FakeCloud(distro))
        self.assertEqual('Some apt error', str(context_manager.exception))
        self.assertIn('Package update failed\nTraceback', self.logs.getvalue())

    @mock.patch('cloudinit.config.cc_snap.util.is_container')
    def test_maybe_install_squashfuse_happy_path(self, m_container):
        """maybe_install_squashfuse logs and raises package install errors."""
        m_container.return_value = True
        distro = mock.MagicMock()  # No errors raised
        maybe_install_squashfuse(cloud=FakeCloud(distro))
        self.assertEqual(
            [mock.call()], distro.update_package_sources.call_args_list)
        self.assertEqual(
            [mock.call(['squashfuse'])],
            distro.install_packages.call_args_list)

# vi: ts=4 expandtab
