# This file is part of cloud-init. See LICENSE file for license information.
import textwrap

import pytest
import responses

from cloudinit import util
from cloudinit.config import cc_puppet
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.distros import PackageInstallerError
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import CiTestCase, mock, skipUnlessJsonSchema
from tests.unittests.util import get_cloud


@pytest.fixture
def fake_tempdir(mocker, tmpdir):
    mocker.patch(
        "cloudinit.config.cc_puppet.temp_utils.tempdir"
    ).return_value.__enter__.return_value = str(tmpdir)


@mock.patch("cloudinit.config.cc_puppet.subp.subp")
class TestManagePuppetServices(CiTestCase):
    def setUp(self):
        super(TestManagePuppetServices, self).setUp()
        self.cloud = get_cloud()

    def test_wb_manage_puppet_services_enables_puppet_systemctl(
        self,
        m_subp,
    ):
        cc_puppet._manage_puppet_services(self.cloud, "enable")
        expected_calls = [
            mock.call(
                ["systemctl", "enable", "puppet-agent.service"],
                capture=True,
                rcs=None,
            )
        ]
        self.assertIn(expected_calls, m_subp.call_args_list)

    def test_wb_manage_puppet_services_starts_puppet_systemctl(
        self,
        m_subp,
    ):
        cc_puppet._manage_puppet_services(self.cloud, "start")
        expected_calls = [
            mock.call(
                ["systemctl", "start", "puppet-agent.service"],
                capture=True,
                rcs=None,
            )
        ]
        self.assertIn(expected_calls, m_subp.call_args_list)

    def test_enable_fallback_on_failure(self, m_subp):
        m_subp.side_effect = (ProcessExecutionError, 0)
        cc_puppet._manage_puppet_services(self.cloud, "enable")
        expected_calls = [
            mock.call(
                ["systemctl", "enable", "puppet-agent.service"],
                capture=True,
                rcs=None,
            ),
            mock.call(
                ["systemctl", "enable", "puppet.service"],
                capture=True,
                rcs=None,
            ),
        ]
        self.assertEqual(expected_calls, m_subp.call_args_list)


@mock.patch("cloudinit.config.cc_puppet._manage_puppet_services")
class TestPuppetHandle(CiTestCase):
    with_logs = True

    def setUp(self):
        super(TestPuppetHandle, self).setUp()
        self.new_root = self.tmp_dir()
        self.conf = self.tmp_path("puppet.conf")
        self.csr_attributes_path = self.tmp_path("csr_attributes.yaml")
        self.cloud = get_cloud()

    def test_skips_missing_puppet_key_in_cloudconfig(self, m_man_puppet):
        """Cloud-config containing no 'puppet' key is skipped."""

        cfg = {}
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertIn("no 'puppet' configuration found", self.logs.getvalue())
        self.assertEqual(0, m_man_puppet.call_count)

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_config_starts_puppet_service(self, m_subp, m_man_puppet):
        """Cloud-config 'puppet' configuration starts puppet."""

        cfg = {"puppet": {"install": False}}
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertEqual(2, m_man_puppet.call_count)
        expected_calls = [
            mock.call(self.cloud, "enable"),
            mock.call(self.cloud, "start"),
        ]
        self.assertEqual(expected_calls, m_man_puppet.call_args_list)

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_empty_puppet_config_installs_puppet(self, m_subp, m_man_puppet):
        """Cloud-config empty 'puppet' configuration installs latest puppet."""

        self.cloud.distro = mock.MagicMock()
        cfg = {"puppet": {}}
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertEqual(
            [mock.call(["puppet-agent"])],
            self.cloud.distro.install_packages.call_args_list,
        )

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_config_installs_puppet_on_true(self, m_subp, _):
        """Cloud-config with 'puppet' key installs when 'install' is True."""

        self.cloud.distro = mock.MagicMock()
        cfg = {"puppet": {"install": True}}
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertIn(
            [mock.call(["puppet-agent"])],
            self.cloud.distro.install_packages.call_args_list,
        )

    @mock.patch("cloudinit.config.cc_puppet.install_puppet_aio", autospec=True)
    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_config_installs_puppet_aio(self, m_subp, m_aio, _):
        """Cloud-config with 'puppet' key installs
        when 'install_type' is 'aio'."""
        distro = mock.MagicMock()
        self.cloud.distro = distro
        cfg = {"puppet": {"install": True, "install_type": "aio"}}
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        m_aio.assert_called_with(
            distro, cc_puppet.AIO_INSTALL_URL, None, None, True
        )

    @mock.patch("cloudinit.config.cc_puppet.install_puppet_aio", autospec=True)
    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_config_installs_puppet_aio_with_version(
        self, m_subp, m_aio, _
    ):
        """Cloud-config with 'puppet' key installs
        when 'install_type' is 'aio' and 'version' is specified."""
        distro = mock.MagicMock()
        self.cloud.distro = distro
        cfg = {
            "puppet": {
                "install": True,
                "version": "6.24.0",
                "install_type": "aio",
            }
        }
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        m_aio.assert_called_with(
            distro, cc_puppet.AIO_INSTALL_URL, "6.24.0", None, True
        )

    @mock.patch("cloudinit.config.cc_puppet.install_puppet_aio", autospec=True)
    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_config_installs_puppet_aio_with_collection(
        self, m_subp, m_aio, _
    ):
        """Cloud-config with 'puppet' key installs
        when 'install_type' is 'aio' and 'collection' is specified."""
        distro = mock.MagicMock()
        self.cloud.distro = distro
        cfg = {
            "puppet": {
                "install": True,
                "collection": "puppet6",
                "install_type": "aio",
            }
        }
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        m_aio.assert_called_with(
            distro, cc_puppet.AIO_INSTALL_URL, None, "puppet6", True
        )

    @mock.patch("cloudinit.config.cc_puppet.install_puppet_aio", autospec=True)
    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_config_installs_puppet_aio_with_custom_url(
        self, m_subp, m_aio, _
    ):
        """Cloud-config with 'puppet' key installs
        when 'install_type' is 'aio' and 'aio_install_url' is specified."""
        distro = mock.MagicMock()
        self.cloud.distro = distro
        cfg = {
            "puppet": {
                "install": True,
                "aio_install_url": "http://test.url/path/to/script.sh",
                "install_type": "aio",
            }
        }
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        m_aio.assert_called_with(
            distro, "http://test.url/path/to/script.sh", None, None, True
        )

    @mock.patch("cloudinit.config.cc_puppet.install_puppet_aio", autospec=True)
    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_config_installs_puppet_aio_without_cleanup(
        self, m_subp, m_aio, _
    ):
        """Cloud-config with 'puppet' key installs
        when 'install_type' is 'aio' and no cleanup."""
        distro = mock.MagicMock()
        self.cloud.distro = distro
        cfg = {
            "puppet": {
                "install": True,
                "cleanup": False,
                "install_type": "aio",
            }
        }
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        m_aio.assert_called_with(
            distro, cc_puppet.AIO_INSTALL_URL, None, None, False
        )

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_config_installs_puppet_version(self, m_subp, _):
        """Cloud-config 'puppet' configuration can specify a version."""

        self.cloud.distro = mock.MagicMock()
        cfg = {"puppet": {"version": "3.8"}}
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertEqual(
            [mock.call([["puppet-agent", "3.8"]])],
            self.cloud.distro.install_packages.call_args_list,
        )

    @mock.patch("cloudinit.config.cc_puppet.get_config_value")
    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_config_updates_puppet_conf(
        self, m_subp, m_default, m_man_puppet
    ):
        """When 'conf' is provided update values in PUPPET_CONF_PATH."""

        def _fake_get_config_value(puppet_bin, setting):
            return self.conf

        m_default.side_effect = _fake_get_config_value

        cfg = {
            "puppet": {
                "conf": {"agent": {"server": "puppetserver.example.org"}}
            }
        }
        util.write_file(self.conf, "[agent]\nserver = origpuppet\nother = 3")
        self.cloud.distro = mock.MagicMock()
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        content = util.load_text_file(self.conf)
        expected = "[agent]\nserver = puppetserver.example.org\nother = 3\n\n"
        self.assertEqual(expected, content)

    @mock.patch("cloudinit.config.cc_puppet.get_config_value")
    @mock.patch("cloudinit.config.cc_puppet.subp.subp")
    def test_puppet_writes_csr_attributes_file(
        self, m_subp, m_default, m_man_puppet
    ):
        """When csr_attributes is provided
        creates file in PUPPET_CSR_ATTRIBUTES_PATH."""

        def _fake_get_config_value(puppet_bin, setting):
            return self.csr_attributes_path

        m_default.side_effect = _fake_get_config_value

        self.cloud.distro = mock.MagicMock()
        cfg = {
            "puppet": {
                "csr_attributes": {
                    "custom_attributes": {
                        "1.2.840.113549.1.9.7": (
                            "342thbjkt82094y0uthhor289jnqthpc2290"
                        )
                    },
                    "extension_requests": {
                        "pp_uuid": "ED803750-E3C7-44F5-BB08-41A04433FE2E",
                        "pp_image_name": "my_ami_image",
                        "pp_preshared_key": (
                            "342thbjkt82094y0uthhor289jnqthpc2290"
                        ),
                    },
                }
            }
        }
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        content = util.load_text_file(self.csr_attributes_path)
        expected = textwrap.dedent(
            """\
            custom_attributes:
              1.2.840.113549.1.9.7: 342thbjkt82094y0uthhor289jnqthpc2290
            extension_requests:
              pp_image_name: my_ami_image
              pp_preshared_key: 342thbjkt82094y0uthhor289jnqthpc2290
              pp_uuid: ED803750-E3C7-44F5-BB08-41A04433FE2E
            """
        )
        self.assertEqual(expected, content)

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_runs_puppet_if_requested(self, m_subp, m_man_puppet):
        """Run puppet with default args if 'exec' is set to True."""

        cfg = {"puppet": {"exec": True}}
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertEqual(2, m_man_puppet.call_count)
        expected_calls = [
            mock.call(self.cloud, "enable"),
            mock.call(self.cloud, "start"),
        ]
        self.assertEqual(expected_calls, m_man_puppet.call_args_list)
        self.assertIn(
            [mock.call(["puppet", "agent", "--test"], capture=False)],
            m_subp.call_args_list,
        )

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_starts_puppetd(self, m_subp, m_man_puppet):
        """Run puppet with default args if 'exec' is set to True."""

        cfg = {"puppet": {}}
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertEqual(2, m_man_puppet.call_count)
        expected_calls = [
            mock.call(self.cloud, "enable"),
            mock.call(self.cloud, "start"),
        ]
        self.assertEqual(expected_calls, m_man_puppet.call_args_list)

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_skips_puppetd(self, m_subp, m_man_puppet):
        """Run puppet with default args if 'exec' is set to True."""

        cfg = {"puppet": {"start_service": False}}
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertEqual(0, m_man_puppet.call_count)
        self.assertNotIn(
            [mock.call(["systemctl", "start", "puppet-agent"], capture=False)],
            m_subp.call_args_list,
        )

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_runs_puppet_with_args_list_if_requested(
        self, m_subp, m_man_puppet
    ):
        """Run puppet with 'exec_args' list if 'exec' is set to True."""

        cfg = {
            "puppet": {
                "exec": True,
                "exec_args": ["--onetime", "--detailed-exitcodes"],
            }
        }
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertEqual(2, m_man_puppet.call_count)
        self.assertIn(
            [
                mock.call(
                    ["puppet", "agent", "--onetime", "--detailed-exitcodes"],
                    capture=False,
                )
            ],
            m_subp.call_args_list,
        )

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_runs_puppet_with_args_string_if_requested(
        self, m_subp, m_man_puppet
    ):
        """Run puppet with 'exec_args' string if 'exec' is set to True."""

        cfg = {
            "puppet": {
                "exec": True,
                "exec_args": "--onetime --detailed-exitcodes",
            }
        }
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertEqual(2, m_man_puppet.call_count)
        self.assertIn(
            [
                mock.call(
                    ["puppet", "agent", "--onetime", "--detailed-exitcodes"],
                    capture=False,
                )
            ],
            m_subp.call_args_list,
        )

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_falls_back_to_older_name(self, m_subp, m_man_puppet):
        cfg = {"puppet": {}}
        with mock.patch(
            "tests.unittests.util.MockDistro.install_packages"
        ) as install_pkg:
            # puppet-agent not installed, but puppet is
            install_pkg.side_effect = (PackageInstallerError, 0)

            cc_puppet.handle("notimportant", cfg, self.cloud, None)
            expected_calls = [
                mock.call(self.cloud, "enable"),
                mock.call(self.cloud, "start"),
            ]
            self.assertEqual(expected_calls, m_man_puppet.call_args_list)

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_with_conf_package_name_fails(self, m_subp, m_man_puppet):
        cfg = {"puppet": {"package_name": "puppet"}}
        with mock.patch(
            "tests.unittests.util.MockDistro.install_packages"
        ) as install_pkg:
            # puppet-agent not installed, but puppet is
            install_pkg.side_effect = (ProcessExecutionError, 0)
            with pytest.raises(ProcessExecutionError):
                cc_puppet.handle("notimportant", cfg, self.cloud, None)
            self.assertEqual(0, m_man_puppet.call_count)
            self.assertNotIn(
                [
                    mock.call(
                        ["systemctl", "start", "puppet-agent"], capture=True
                    )
                ],
                m_subp.call_args_list,
            )

    @mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=("", ""))
    def test_puppet_with_conf_package_name_success(self, m_subp, m_man_puppet):
        cfg = {"puppet": {"package_name": "puppet"}}
        cc_puppet.handle("notimportant", cfg, self.cloud, None)
        self.assertEqual(2, m_man_puppet.call_count)


URL_MOCK = mock.Mock()
URL_MOCK.contents = b'#!/bin/bash\necho "Hi Mom"'


@pytest.mark.usefixtures("fake_tempdir")
@mock.patch("cloudinit.config.cc_puppet.subp.subp", return_value=(None, None))
@mock.patch(
    "cloudinit.config.cc_puppet.url_helper.readurl",
    return_value=URL_MOCK,
    autospec=True,
)
class TestInstallPuppetAio:
    @pytest.mark.parametrize(
        "args, expected_subp_call_args_list, expected_readurl_call_args_list",
        [
            pytest.param(
                [],
                [mock.call([mock.ANY, "--cleanup"], capture=False)],
                [
                    mock.call(
                        url="https://raw.githubusercontent.com/puppetlabs/install-puppet/main/install.sh",  # noqa: E501
                        retries=5,
                    )
                ],
                id="default_arguments",
            ),
            pytest.param(
                ["http://custom.url/path/to/script.sh"],
                [mock.call([mock.ANY, "--cleanup"], capture=False)],
                [
                    mock.call(
                        url="http://custom.url/path/to/script.sh", retries=5
                    )
                ],
                id="custom_url",
            ),
            pytest.param(
                [cc_puppet.AIO_INSTALL_URL, "7.6.0"],
                [
                    mock.call(
                        [mock.ANY, "-v", "7.6.0", "--cleanup"], capture=False
                    )
                ],
                [mock.call(url=cc_puppet.AIO_INSTALL_URL, retries=5)],
                id="version",
            ),
            pytest.param(
                [cc_puppet.AIO_INSTALL_URL, None, "puppet6-nightly"],
                [
                    mock.call(
                        [mock.ANY, "-c", "puppet6-nightly", "--cleanup"],
                        capture=False,
                    )
                ],
                [mock.call(url=cc_puppet.AIO_INSTALL_URL, retries=5)],
                id="collection",
            ),
            pytest.param(
                [cc_puppet.AIO_INSTALL_URL, None, None, False],
                [mock.call([mock.ANY], capture=False)],
                [mock.call(url=cc_puppet.AIO_INSTALL_URL, retries=5)],
                id="no_cleanup",
            ),
        ],
    )
    @responses.activate
    def test_install_puppet_aio(
        self,
        m_readurl,
        m_subp,
        args,
        expected_subp_call_args_list,
        expected_readurl_call_args_list,
        tmpdir,
    ):
        distro = mock.Mock()
        distro.get_tmp_exec_path.return_value = str(tmpdir)
        cc_puppet.install_puppet_aio(distro, *args)
        assert expected_readurl_call_args_list == m_readurl.call_args_list
        assert expected_subp_call_args_list == m_subp.call_args_list


class TestPuppetSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Some validity checks
            ({"puppet": {"conf": {"main": {"key": "val"}}}}, None),
            ({"puppet": {"conf": {"server": {"key": "val"}}}}, None),
            ({"puppet": {"conf": {"agent": {"key": "val"}}}}, None),
            ({"puppet": {"conf": {"user": {"key": "val"}}}}, None),
            ({"puppet": {"conf": {"main": {}}}}, None),
            (
                {
                    "puppet": {
                        "conf": {
                            "agent": {
                                "server": "val",
                                "certname": "val",
                            }
                        }
                    }
                },
                None,
            ),
            (
                {
                    "puppet": {
                        "conf": {
                            "main": {"key": "val"},
                            "server": {"key": "val"},
                            "agent": {"key": "val"},
                            "user": {"key": "val"},
                            "ca_cert": "val",
                        }
                    }
                },
                None,
            ),
            (
                {
                    "puppet": {
                        "csr_attributes": {
                            "custom_attributes": {"key": "val"},
                            "extension_requests": {"key": "val"},
                        },
                    }
                },
                None,
            ),
            # Invalid package
            (
                {"puppet": {"install_type": "package"}},
                r"'package' is not one of \['packages', 'aio'\]",
            ),
            # Additional key in "conf"
            ({"puppet": {"conf": {"test": {}}}}, "'test' was unexpected"),
            # Additional key in "csr_attributes"
            (
                {"puppet": {"csr_attributes": {"test": {}}}},
                "'test' was unexpected",
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
