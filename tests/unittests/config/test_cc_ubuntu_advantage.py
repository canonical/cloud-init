# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import subp
from cloudinit.config.cc_ubuntu_advantage import (
    configure_ua,
    handle,
    maybe_install_ua_tools,
    schema,
)
from cloudinit.config.schema import validate_cloudconfig_schema
from tests.unittests.helpers import (
    CiTestCase,
    SchemaTestCaseMixin,
    mock,
    skipUnlessJsonSchema,
)

# Module path used in mocks
MPATH = "cloudinit.config.cc_ubuntu_advantage"


class FakeCloud(object):
    def __init__(self, distro):
        self.distro = distro


class TestConfigureUA(CiTestCase):

    with_logs = True
    allowed_subp = [CiTestCase.SUBP_SHELL_TRUE]

    def setUp(self):
        super(TestConfigureUA, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch("%s.subp.subp" % MPATH)
    def test_configure_ua_attach_error(self, m_subp):
        """Errors from ua attach command are raised."""
        m_subp.side_effect = subp.ProcessExecutionError(
            "Invalid token SomeToken"
        )
        with self.assertRaises(RuntimeError) as context_manager:
            configure_ua(token="SomeToken")
        self.assertEqual(
            "Failure attaching Ubuntu Advantage:\nUnexpected error while"
            " running command.\nCommand: -\nExit code: -\nReason: -\n"
            "Stdout: Invalid token SomeToken\nStderr: -",
            str(context_manager.exception),
        )

    @mock.patch("%s.subp.subp" % MPATH)
    def test_configure_ua_attach_with_token(self, m_subp):
        """When token is provided, attach the machine to ua using the token."""
        configure_ua(token="SomeToken")
        m_subp.assert_called_once_with(["ua", "attach", "SomeToken"])
        self.assertEqual(
            "DEBUG: Attaching to Ubuntu Advantage. ua attach SomeToken\n",
            self.logs.getvalue(),
        )

    @mock.patch("%s.subp.subp" % MPATH)
    def test_configure_ua_attach_on_service_error(self, m_subp):
        """all services should be enabled and then any failures raised"""

        def fake_subp(cmd, capture=None):
            fail_cmds = [
                ["ua", "enable", "--assume-yes", svc] for svc in ["esm", "cc"]
            ]
            if cmd in fail_cmds and capture:
                svc = cmd[-1]
                raise subp.ProcessExecutionError(
                    "Invalid {} credentials".format(svc.upper())
                )

        m_subp.side_effect = fake_subp

        with self.assertRaises(RuntimeError) as context_manager:
            configure_ua(token="SomeToken", enable=["esm", "cc", "fips"])
        self.assertEqual(
            m_subp.call_args_list,
            [
                mock.call(["ua", "attach", "SomeToken"]),
                mock.call(
                    ["ua", "enable", "--assume-yes", "esm"], capture=True
                ),
                mock.call(
                    ["ua", "enable", "--assume-yes", "cc"], capture=True
                ),
                mock.call(
                    ["ua", "enable", "--assume-yes", "fips"], capture=True
                ),
            ],
        )
        self.assertIn(
            'WARNING: Failure enabling "esm":\nUnexpected error'
            " while running command.\nCommand: -\nExit code: -\nReason: -\n"
            "Stdout: Invalid ESM credentials\nStderr: -\n",
            self.logs.getvalue(),
        )
        self.assertIn(
            'WARNING: Failure enabling "cc":\nUnexpected error'
            " while running command.\nCommand: -\nExit code: -\nReason: -\n"
            "Stdout: Invalid CC credentials\nStderr: -\n",
            self.logs.getvalue(),
        )
        self.assertEqual(
            'Failure enabling Ubuntu Advantage service(s): "esm", "cc"',
            str(context_manager.exception),
        )

    @mock.patch("%s.subp.subp" % MPATH)
    def test_configure_ua_attach_with_empty_services(self, m_subp):
        """When services is an empty list, do not auto-enable attach."""
        configure_ua(token="SomeToken", enable=[])
        m_subp.assert_called_once_with(["ua", "attach", "SomeToken"])
        self.assertEqual(
            "DEBUG: Attaching to Ubuntu Advantage. ua attach SomeToken\n",
            self.logs.getvalue(),
        )

    @mock.patch("%s.subp.subp" % MPATH)
    def test_configure_ua_attach_with_specific_services(self, m_subp):
        """When services a list, only enable specific services."""
        configure_ua(token="SomeToken", enable=["fips"])
        self.assertEqual(
            m_subp.call_args_list,
            [
                mock.call(["ua", "attach", "SomeToken"]),
                mock.call(
                    ["ua", "enable", "--assume-yes", "fips"], capture=True
                ),
            ],
        )
        self.assertEqual(
            "DEBUG: Attaching to Ubuntu Advantage. ua attach SomeToken\n",
            self.logs.getvalue(),
        )

    @mock.patch("%s.maybe_install_ua_tools" % MPATH, mock.MagicMock())
    @mock.patch("%s.subp.subp" % MPATH)
    def test_configure_ua_attach_with_string_services(self, m_subp):
        """When services a string, treat as singleton list and warn"""
        configure_ua(token="SomeToken", enable="fips")
        self.assertEqual(
            m_subp.call_args_list,
            [
                mock.call(["ua", "attach", "SomeToken"]),
                mock.call(
                    ["ua", "enable", "--assume-yes", "fips"], capture=True
                ),
            ],
        )
        self.assertEqual(
            "WARNING: ubuntu_advantage: enable should be a list, not a"
            " string; treating as a single enable\n"
            "DEBUG: Attaching to Ubuntu Advantage. ua attach SomeToken\n",
            self.logs.getvalue(),
        )

    @mock.patch("%s.subp.subp" % MPATH)
    def test_configure_ua_attach_with_weird_services(self, m_subp):
        """When services not string or list, warn but still attach"""
        configure_ua(token="SomeToken", enable={"deffo": "wont work"})
        self.assertEqual(
            m_subp.call_args_list, [mock.call(["ua", "attach", "SomeToken"])]
        )
        self.assertEqual(
            "WARNING: ubuntu_advantage: enable should be a list, not a"
            " dict; skipping enabling services\n"
            "DEBUG: Attaching to Ubuntu Advantage. ua attach SomeToken\n",
            self.logs.getvalue(),
        )


@skipUnlessJsonSchema()
class TestSchema(CiTestCase, SchemaTestCaseMixin):

    with_logs = True
    schema = schema

    @mock.patch("%s.maybe_install_ua_tools" % MPATH)
    @mock.patch("%s.configure_ua" % MPATH)
    def test_schema_warns_on_ubuntu_advantage_not_dict(self, _cfg, _):
        """If ubuntu_advantage configuration is not a dict, emit a warning."""
        validate_cloudconfig_schema({"ubuntu_advantage": "wrong type"}, schema)
        self.assertEqual(
            "WARNING: Invalid cloud-config provided:\nubuntu_advantage:"
            " 'wrong type' is not of type 'object'\n",
            self.logs.getvalue(),
        )

    @mock.patch("%s.maybe_install_ua_tools" % MPATH)
    @mock.patch("%s.configure_ua" % MPATH)
    def test_schema_disallows_unknown_keys(self, _cfg, _):
        """Unknown keys in ubuntu_advantage configuration emit warnings."""
        validate_cloudconfig_schema(
            {"ubuntu_advantage": {"token": "winner", "invalid-key": ""}},
            schema,
        )
        self.assertIn(
            "WARNING: Invalid cloud-config provided:\nubuntu_advantage:"
            " Additional properties are not allowed ('invalid-key' was"
            " unexpected)",
            self.logs.getvalue(),
        )

    @mock.patch("%s.maybe_install_ua_tools" % MPATH)
    @mock.patch("%s.configure_ua" % MPATH)
    def test_warn_schema_requires_token(self, _cfg, _):
        """Warn if ubuntu_advantage configuration lacks token."""
        validate_cloudconfig_schema(
            {"ubuntu_advantage": {"enable": ["esm"]}}, schema
        )
        self.assertEqual(
            "WARNING: Invalid cloud-config provided:\nubuntu_advantage:"
            " 'token' is a required property\n",
            self.logs.getvalue(),
        )

    @mock.patch("%s.maybe_install_ua_tools" % MPATH)
    @mock.patch("%s.configure_ua" % MPATH)
    def test_warn_schema_services_is_not_list_or_dict(self, _cfg, _):
        """Warn when ubuntu_advantage:enable config is not a list."""
        validate_cloudconfig_schema(
            {"ubuntu_advantage": {"enable": "needslist"}}, schema
        )
        self.assertEqual(
            "WARNING: Invalid cloud-config provided:\nubuntu_advantage:"
            " 'token' is a required property\nubuntu_advantage.enable:"
            " 'needslist' is not of type 'array'\n",
            self.logs.getvalue(),
        )


class TestHandle(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestHandle, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch("%s.validate_cloudconfig_schema" % MPATH)
    def test_handle_no_config(self, m_schema):
        """When no ua-related configuration is provided, nothing happens."""
        cfg = {}
        handle("ua-test", cfg=cfg, cloud=None, log=self.logger, args=None)
        self.assertIn(
            "DEBUG: Skipping module named ua-test, no 'ubuntu_advantage'"
            " configuration found",
            self.logs.getvalue(),
        )
        m_schema.assert_not_called()

    @mock.patch("%s.configure_ua" % MPATH)
    @mock.patch("%s.maybe_install_ua_tools" % MPATH)
    def test_handle_tries_to_install_ubuntu_advantage_tools(
        self, m_install, m_cfg
    ):
        """If ubuntu_advantage is provided, try installing ua-tools package."""
        cfg = {"ubuntu_advantage": {"token": "valid"}}
        mycloud = FakeCloud(None)
        handle("nomatter", cfg=cfg, cloud=mycloud, log=self.logger, args=None)
        m_install.assert_called_once_with(mycloud)

    @mock.patch("%s.configure_ua" % MPATH)
    @mock.patch("%s.maybe_install_ua_tools" % MPATH)
    def test_handle_passes_credentials_and_services_to_configure_ua(
        self, m_install, m_configure_ua
    ):
        """All ubuntu_advantage config keys are passed to configure_ua."""
        cfg = {"ubuntu_advantage": {"token": "token", "enable": ["esm"]}}
        handle("nomatter", cfg=cfg, cloud=None, log=self.logger, args=None)
        m_configure_ua.assert_called_once_with(token="token", enable=["esm"])

    @mock.patch("%s.maybe_install_ua_tools" % MPATH, mock.MagicMock())
    @mock.patch("%s.configure_ua" % MPATH)
    def test_handle_warns_on_deprecated_ubuntu_advantage_key_w_config(
        self, m_configure_ua
    ):
        """Warning when ubuntu-advantage key is present with new config"""
        cfg = {"ubuntu-advantage": {"token": "token", "enable": ["esm"]}}
        handle("nomatter", cfg=cfg, cloud=None, log=self.logger, args=None)
        self.assertEqual(
            'WARNING: Deprecated configuration key "ubuntu-advantage"'
            ' provided. Expected underscore delimited "ubuntu_advantage";'
            " will attempt to continue.",
            self.logs.getvalue().splitlines()[0],
        )
        m_configure_ua.assert_called_once_with(token="token", enable=["esm"])

    def test_handle_error_on_deprecated_commands_key_dashed(self):
        """Error when commands is present in ubuntu-advantage key."""
        cfg = {"ubuntu-advantage": {"commands": "nogo"}}
        with self.assertRaises(RuntimeError) as context_manager:
            handle("nomatter", cfg=cfg, cloud=None, log=self.logger, args=None)
        self.assertEqual(
            'Deprecated configuration "ubuntu-advantage: commands" provided.'
            ' Expected "token"',
            str(context_manager.exception),
        )

    def test_handle_error_on_deprecated_commands_key_underscored(self):
        """Error when commands is present in ubuntu_advantage key."""
        cfg = {"ubuntu_advantage": {"commands": "nogo"}}
        with self.assertRaises(RuntimeError) as context_manager:
            handle("nomatter", cfg=cfg, cloud=None, log=self.logger, args=None)
        self.assertEqual(
            'Deprecated configuration "ubuntu-advantage: commands" provided.'
            ' Expected "token"',
            str(context_manager.exception),
        )

    @mock.patch("%s.maybe_install_ua_tools" % MPATH, mock.MagicMock())
    @mock.patch("%s.configure_ua" % MPATH)
    def test_handle_prefers_new_style_config(self, m_configure_ua):
        """ubuntu_advantage should be preferred over ubuntu-advantage"""
        cfg = {
            "ubuntu-advantage": {"token": "nope", "enable": ["wrong"]},
            "ubuntu_advantage": {"token": "token", "enable": ["esm"]},
        }
        handle("nomatter", cfg=cfg, cloud=None, log=self.logger, args=None)
        self.assertEqual(
            'WARNING: Deprecated configuration key "ubuntu-advantage"'
            ' provided. Expected underscore delimited "ubuntu_advantage";'
            " will attempt to continue.",
            self.logs.getvalue().splitlines()[0],
        )
        m_configure_ua.assert_called_once_with(token="token", enable=["esm"])


class TestMaybeInstallUATools(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestMaybeInstallUATools, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch("%s.subp.which" % MPATH)
    def test_maybe_install_ua_tools_noop_when_ua_tools_present(self, m_which):
        """Do nothing if ubuntu-advantage-tools already exists."""
        m_which.return_value = "/usr/bin/ua"  # already installed
        distro = mock.MagicMock()
        distro.update_package_sources.side_effect = RuntimeError(
            "Some apt error"
        )
        maybe_install_ua_tools(cloud=FakeCloud(distro))  # No RuntimeError

    @mock.patch("%s.subp.which" % MPATH)
    def test_maybe_install_ua_tools_raises_update_errors(self, m_which):
        """maybe_install_ua_tools logs and raises apt update errors."""
        m_which.return_value = None
        distro = mock.MagicMock()
        distro.update_package_sources.side_effect = RuntimeError(
            "Some apt error"
        )
        with self.assertRaises(RuntimeError) as context_manager:
            maybe_install_ua_tools(cloud=FakeCloud(distro))
        self.assertEqual("Some apt error", str(context_manager.exception))
        self.assertIn("Package update failed\nTraceback", self.logs.getvalue())

    @mock.patch("%s.subp.which" % MPATH)
    def test_maybe_install_ua_raises_install_errors(self, m_which):
        """maybe_install_ua_tools logs and raises package install errors."""
        m_which.return_value = None
        distro = mock.MagicMock()
        distro.update_package_sources.return_value = None
        distro.install_packages.side_effect = RuntimeError(
            "Some install error"
        )
        with self.assertRaises(RuntimeError) as context_manager:
            maybe_install_ua_tools(cloud=FakeCloud(distro))
        self.assertEqual("Some install error", str(context_manager.exception))
        self.assertIn(
            "Failed to install ubuntu-advantage-tools\n", self.logs.getvalue()
        )

    @mock.patch("%s.subp.which" % MPATH)
    def test_maybe_install_ua_tools_happy_path(self, m_which):
        """maybe_install_ua_tools installs ubuntu-advantage-tools."""
        m_which.return_value = None
        distro = mock.MagicMock()  # No errors raised
        maybe_install_ua_tools(cloud=FakeCloud(distro))
        distro.update_package_sources.assert_called_once_with()
        distro.install_packages.assert_called_once_with(
            ["ubuntu-advantage-tools"]
        )


# vi: ts=4 expandtab
