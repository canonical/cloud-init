# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os

import pytest

from cloudinit import helpers, util
from cloudinit.config.cc_snap import add_assertions, handle, run_commands
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import CiTestCase, mock, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

M_PATH = "cloudinit.config.cc_snap."
ASSERTIONS_FILE = "/var/lib/cloud/instance/snapd.assertions"

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


@pytest.fixture()
def fake_cloud(tmpdir):
    paths = helpers.Paths(
        {
            "cloud_dir": tmpdir.join("cloud"),
            "run_dir": tmpdir.join("cloud-init"),
            "templates_dir": tmpdir.join("templates"),
        }
    )
    cloud = get_cloud(paths=paths)
    yield cloud


class TestAddAssertions:
    @mock.patch("cloudinit.config.cc_snap.subp.subp")
    def test_add_assertions_on_empty_list(self, m_subp, caplog, tmpdir):
        """When provided with an empty list, add_assertions does nothing."""
        assert_file = tmpdir.join("snapd.assertions")
        add_assertions([], assert_file)
        assert not caplog.text
        assert 0 == m_subp.call_count

    def test_add_assertions_on_non_list_or_dict(self, tmpdir):
        """When provided an invalid type, add_assertions raises an error."""
        assert_file = tmpdir.join("snapd.assertions")
        with pytest.raises(
            TypeError,
            match="assertion parameter was not a list or dict: I'm Not Valid",
        ):
            add_assertions("I'm Not Valid", assert_file)

    @mock.patch("cloudinit.config.cc_snap.subp.subp")
    def test_add_assertions_adds_assertions_as_list(
        self, m_subp, caplog, tmpdir
    ):
        """When provided with a list, add_assertions adds all assertions."""
        assert_file = tmpdir.join("snapd.assertions")
        assertions = [SYSTEM_USER_ASSERTION, ACCOUNT_ASSERTION]
        add_assertions(assertions, assert_file)
        assert "Importing user-provided snap assertions" in caplog.text
        assert "sertions" in caplog.text
        assert [
            mock.call(["snap", "ack", assert_file], capture=True)
        ] == m_subp.call_args_list
        compare_file = tmpdir.join("comparison")
        util.write_file(compare_file, "\n".join(assertions).encode("utf-8"))
        assert util.load_text_file(compare_file) == util.load_text_file(
            assert_file
        )

    @mock.patch("cloudinit.config.cc_snap.subp.subp")
    def test_add_assertions_adds_assertions_as_dict(
        self, m_subp, caplog, tmpdir
    ):
        """When provided with a dict, add_assertions adds all assertions."""
        assert_file = tmpdir.join("snapd.assertions")
        assertions = {"00": SYSTEM_USER_ASSERTION, "01": ACCOUNT_ASSERTION}
        add_assertions(assertions, assert_file)
        assert "Importing user-provided snap assertions" in caplog.text
        assert (
            M_PATH[:-1],
            logging.DEBUG,
            "Snap acking: ['type: system-user', 'authority-id: "
            "LqvZQdfyfGlYvtep4W6Oj6pFXP9t1Ksp']",
        ) in caplog.record_tuples
        assert (
            M_PATH[:-1],
            logging.DEBUG,
            "Snap acking: ['type: account-key', 'authority-id: canonical']",
        ) in caplog.record_tuples
        assert [
            mock.call(["snap", "ack", assert_file], capture=True)
        ] == m_subp.call_args_list
        compare_file = tmpdir.join("comparison")
        combined = "\n".join(assertions.values())
        util.write_file(compare_file, combined.encode("utf-8"))
        assert util.load_text_file(compare_file) == util.load_text_file(
            assert_file
        )


class TestRunCommands(CiTestCase):
    with_logs = True
    allowed_subp = [CiTestCase.SUBP_SHELL_TRUE]

    def setUp(self):
        super(TestRunCommands, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch("cloudinit.config.cc_snap.subp.subp")
    def test_run_commands_on_empty_list(self, m_subp):
        """When provided with an empty list, run_commands does nothing."""
        run_commands([])
        self.assertEqual("", self.logs.getvalue())
        m_subp.assert_not_called()

    def test_run_commands_on_non_list_or_dict(self):
        """When provided an invalid type, run_commands raises an error."""
        with self.assertRaises(TypeError) as context_manager:
            run_commands(commands="I'm Not Valid")
        self.assertEqual(
            "commands parameter was not a list or dict: I'm Not Valid",
            str(context_manager.exception),
        )


@pytest.mark.allow_all_subp
class TestCommands:
    def test_run_command_dict_sorted_as_command_script(self, caplog, tmp_path):
        """When commands are a dict, sort them and run."""
        outfile = f"{tmp_path}/output.log"
        cmd1 = f'echo "HI" >> {outfile}'
        cmd2 = f'echo "MOM" >> {outfile}'
        commands = {"02": cmd1, "01": cmd2}
        run_commands(commands=commands)

        expected_messages = ["Running user-provided snap commands"]
        for message in expected_messages:
            assert message in caplog.text
        assert "MOM\nHI\n" == util.load_text_file(outfile)

    def test_run_command_as_lists(self, caplog, tmp_path):
        """When commands are specified as a list, run them in order."""
        outfile = "output.log"

        cmd1 = f'echo "HI" >> {tmp_path}/{outfile}'
        cmd2 = f'echo "MOM" >> {tmp_path}/{outfile}'
        commands = [cmd1, cmd2]
        run_commands(commands=commands)

        assert "Running user-provided snap commands" in caplog.text
        assert "HI\nMOM\n" == util.load_text_file(f"{tmp_path}/{outfile}")
        assert "Non-snap commands in snap config:" in caplog.text


@skipUnlessJsonSchema()
class TestSnapSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Valid
            ({"snap": {"commands": ["valid"]}}, None),
            ({"snap": {"commands": {"01": "also valid"}}}, None),
            ({"snap": {"assertions": ["valid"]}}, None),
            ({"snap": {"assertions": {"01": "also valid"}}}, None),
            ({"snap": {"commands": [["echo", "bye"], ["echo", "bye"]]}}, None),
            ({"snap": {"commands": ["echo bye", "echo bye"]}}, None),
            (
                {
                    "snap": {
                        "commands": {
                            "00": ["echo", "bye"],
                            "01": ["echo", "bye"],
                        }
                    }
                },
                None,
            ),
            (
                {"snap": {"commands": {"00": "echo bye", "01": "echo bye"}}},
                None,
            ),
            # Invalid
            ({"snap": "wrong type"}, "'wrong type' is not of type 'object'"),
            (
                {"snap": {"commands": ["ls"], "invalid-key": ""}},
                "Additional properties are not allowed",
            ),
            ({"snap": {}}, "{} does not have enough properties"),
            (
                {"snap": {"commands": "broken"}},
                "'broken' is not of type 'object', 'array'",
            ),
            ({"snap": {"commands": []}}, r"snap.commands: \[\] is too short"),
            (
                {"snap": {"commands": {}}},
                r"snap.commands: {} does not have enough properties",
            ),
            ({"snap": {"commands": [123]}}, ""),
            ({"snap": {"commands": {"01": 123}}}, ""),
            ({"snap": {"commands": [["snap", "install", 123]]}}, ""),
            ({"snap": {"commands": {"01": ["snap", "install", 123]}}}, ""),
            ({"snap": {"assertions": [123]}}, "123 is not of type 'string'"),
            (
                {"snap": {"assertions": {"01": 123}}},
                "123 is not of type 'string'",
            ),
            (
                {"snap": {"assertions": "broken"}},
                "'broken' is not of type 'object', 'array'",
            ),
            ({"snap": {"assertions": []}}, r"\[\] is too short"),
            (
                {"snap": {"assertions": {}}},
                r"\{} does not have enough properties",
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)


class TestHandle:
    @mock.patch("cloudinit.config.cc_snap.subp.subp")
    def test_handle_adds_assertions(self, m_subp, fake_cloud, tmpdir):
        """Any configured snap assertions are provided to add_assertions."""
        assert_file = os.path.join(
            fake_cloud.paths.get_ipath_cur(), "snapd.assertions"
        )
        compare_file = tmpdir.join("comparison")
        cfg = {
            "snap": {"assertions": [SYSTEM_USER_ASSERTION, ACCOUNT_ASSERTION]}
        }
        handle("snap", cfg=cfg, cloud=fake_cloud, args=None)
        content = "\n".join(cfg["snap"]["assertions"])
        util.write_file(compare_file, content.encode("utf-8"))
        assert util.load_text_file(compare_file) == util.load_text_file(
            assert_file
        )
