import os
import re
from contextlib import nullcontext
from copy import deepcopy
from textwrap import dedent
from typing import Any, Dict
from unittest import mock
from unittest.mock import MagicMock

from pytest import mark, param, raises

from cloudinit import lifecycle
from cloudinit.config import cc_ansible
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import (
    skipUnlessJsonSchema,
    skipUnlessJsonSchemaVersionGreaterThan,
)
from tests.unittests.util import get_cloud

try:
    import pip as _pip  # noqa: F401

    HAS_PIP = True
except ImportError:
    HAS_PIP = False

M_PATH = "cloudinit.config.cc_ansible."
distro_version = dedent(
    """ansible 2.10.8
  config file = None
  configured module search path = ['/home/holmanb/.ansible/plugins/modules', \
  '/usr/share/ansible/plugins/modules']
  ansible python module location = /usr/lib/python3/dist-packages/ansible
  executable location = /usr/bin/ansible
  python version = 3.10.4 (main, Jun 29 2022, 12:14:53) [GCC 11.2.0]"""
)
pip_version = dedent(
    """ansible-pull [core 2.13.2]
  config file = None
  configured module search path = ['/root/.ansible/plugins/modules', \
  '/usr/share/ansible/plugins/modules']
  ansible python module location = /root/.local/lib/python3.8/site-\
  packages/ansible
  ansible collection location = /root/.ansible/collections:\
  /usr/share/ansible/collections
  executable location = /root/.local/lib/python3.8/site-packages/\
  ansible/__main__.py
  python version = 3.8.10 (default, Jun 22 2022, 20:18:18) [GCC 9.4.0]
  jinja version = 3.1.2
  libyaml = True """
)

CFG_CTRL = {
    "ansible": {
        "install_method": "distro",
        "package_name": "ansible-core",
        "ansible_config": "/etc/ansible/ansible.cfg",
        "galaxy": {
            "actions": [["ansible-galaxy", "install", "debops.apt"]],
        },
        "setup_controller": {
            "repositories": [
                {
                    "path": "/home/ansible/public/",
                    "source": "git@github.com:holmanb/ansible-lxd-public.git",
                },
                {
                    "path": "/home/ansible/private/",
                    "source": "git@github.com:holmanb/ansible-lxd-private.git",
                },
                {
                    "path": "/home/ansible/vmboot",
                    "source": "git@github.com:holmanb/vmboot.git",
                },
            ],
            "run_ansible": [
                {
                    "playbook_dir": "/home/ansible/my-repo",
                    "playbook_name": "start-lxd.yml",
                    "timeout": 120,
                    "forks": 1,
                    "private_key": "/home/ansible/.ssh/id_rsa",
                },
                {
                    "playbook_name": "configure-lxd.yml",
                    "become_user": "ansible",
                    "timeout": 120,
                    "forks": 1,
                    "private_key": "/home/ansible/.ssh/id_rsa",
                    "become_password_file": "/path/less/traveled",
                    "connection-password-file": "/path/more/traveled",
                    "module_path": "/path/head/traveled",
                    "vault_password_file": "/path/tail/traveled",
                    "playbook_dir": "/path/to/nowhere",
                    "inventory": "/a/file/as/well",
                },
            ],
        },
    },
}

CFG_FULL_PULL_DICT: Dict[str, Any] = {
    "ansible": {
        "install_method": "distro",
        "package_name": "ansible-core",
        "ansible_config": "/etc/ansible/ansible.cfg",
        "galaxy": {
            "actions": [["ansible-galaxy", "install", "debops.apt"]],
        },
        "pull": {
            "url": "https://github/holmanb/vmboot",
            "playbook_names": ["arch.yml"],
            "accept_host_key": True,
            "clean": True,
            "full": True,
            "diff": False,
            "ssh_common_args": "-y",
            "scp_extra_args": "-l",
            "sftp_extra_args": "-f",
            "checkout": "tree",
            "module_path": "~/.ansible/plugins/modules:"
            "/usr/share/ansible/plugins/modules",
            "timeout": "10",
            "vault_id": "me",
            "connection": "smart",
            "vault_password_file": "/path/to/file",
            "module_name": "git",
            "sleep": "1",
            "tags": "cumulus",
            "skip_tags": "cisco",
            "private_key": "{nope}",
        },
    }
}

CFG_FULL_PULL_LIST: Dict[str, Any] = {
    "ansible": {
        "install_method": "distro",
        "package_name": "ansible-core",
        "ansible_config": "/etc/ansible/ansible.cfg",
        "galaxy": {
            "actions": [["ansible-galaxy", "install", "debops.apt"]],
        },
        "pull": [
            {
                "url": "https://github/holmanb/vmboot",
                "playbook_names": ["arch.yml"],
                "accept_host_key": True,
                "clean": True,
                "full": True,
                "diff": False,
                "ssh_common_args": "-y",
                "scp_extra_args": "-l",
                "sftp_extra_args": "-f",
                "checkout": "tree",
                "module_path": "~/.ansible/plugins/modules:"
                "/usr/share/ansible/plugins/modules",
                "timeout": "10",
                "vault_id": "me",
                "connection": "smart",
                "vault_password_file": "/path/to/file",
                "module_name": "git",
                "sleep": "1",
                "tags": "cumulus",
                "skip_tags": "cisco",
                "private_key": "{nope}",
            }
        ],
    }
}

CFG_MINIMAL_DICT = {
    "ansible": {
        "install_method": "pip",
        "package_name": "ansible",
        "run_user": "ansible",
        "pull": {
            "url": "https://github/holmanb/vmboot",
            "playbook_names": ["ubuntu.yml"],
        },
    }
}

CFG_MINIMAL_LIST = {
    "ansible": {
        "install_method": "pip",
        "package_name": "ansible",
        "run_user": "ansible",
        "pull": [
            {
                "url": "https://github/holmanb/vmboot",
                "playbook_names": ["ubuntu.yml"],
            }
        ],
    }
}


class TestSchema:

    @mark.parametrize(
        ("config", "error_msg"),
        (
            param(
                CFG_MINIMAL_DICT,
                "Expect **ansible.pull** as list of objects",
                id="essentials_dict",
            ),
            param(
                CFG_FULL_PULL_DICT,
                "Expect **ansible.pull** as list of objects",
                id="all-pull-keys-dict",
            ),
        ),
    )
    @skipUnlessJsonSchemaVersionGreaterThan(version=(3, 2, 0))
    def test_schema_validation_deprecations(self, config, error_msg):
        with raises(SchemaValidationError, match=re.escape(error_msg)):
            validate_cloudconfig_schema(config, get_schema(), strict=True)

    @mark.parametrize(
        ("config", "error_msg"),
        (
            param(
                {
                    "ansible": {
                        "install_method": "distro",
                        "pull": {
                            "url": "https://github/holmanb/vmboot",
                            "playbook_names": ["centos.yml"],
                            "dance": "bossa nova",
                        },
                    }
                },
                "Additional properties are not allowed ",
                id="additional-properties-dict",
            ),
            param(
                CFG_CTRL,
                None,
                id="ctrl-keys",
            ),
            param(
                {
                    "ansible": {
                        "install_method": "true",
                        "pull": {
                            "url": "https://github/holmanb/vmboot",
                            "playbook_names": ["debian.yml"],
                        },
                    }
                },
                "'true' is not one of ['distro', 'pip']",
                id="install-type-dict",
            ),
            param(
                {
                    "ansible": {
                        "install_method": "pip",
                        "pull": {
                            "playbook_names": ["fedora.yml"],
                        },
                    }
                },
                "'url' is a required property",
                id="require-url-dict",
            ),
            param(
                {
                    "ansible": {
                        "install_method": "pip",
                        "pull": {
                            "url": "gophers://encrypted-gophers/",
                        },
                    }
                },
                "'playbook_name' is a required property",
                id="require-url-dict",
            ),
            param(
                CFG_MINIMAL_LIST,
                None,
                id="essentials_list",
            ),
            param(
                {
                    "ansible": {
                        "install_method": "distro",
                        "pull": [
                            {
                                "url": "https://github/holmanb/vmboot",
                                "playbook_names": ["centos.yml"],
                                "dance": "bossa nova",
                            }
                        ],
                    }
                },
                "Additional properties are not allowed ",
                id="additional-properties-list",
            ),
            param(
                CFG_FULL_PULL_LIST,
                None,
                id="all-pull-keys-list",
            ),
            param(
                CFG_CTRL,
                None,
                id="ctrl-keys",
            ),
            param(
                {
                    "ansible": {
                        "install_method": "true",
                        "pull": [
                            {
                                "url": "https://github/holmanb/vmboot",
                                "playbook_names": ["debian.yml"],
                            }
                        ],
                    }
                },
                "'true' is not one of ['distro', 'pip']",
                id="install-type-list",
            ),
            param(
                {
                    "ansible": {
                        "install_method": "pip",
                        "pull": [
                            {
                                "playbook_names": ["fedora.yml"],
                            }
                        ],
                    }
                },
                "'url' is a required property",
                id="require-url-list",
            ),
            param(
                {
                    "ansible": {
                        "install_method": "pip",
                        "pull": [
                            {
                                "url": "gophers://encrypted-gophers/",
                            }
                        ],
                    }
                },
                "'playbook_name' is a required property",
                id="require-url-list",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with raises(SchemaValidationError, match=re.escape(error_msg)):
                validate_cloudconfig_schema(config, get_schema(), strict=True)


class TestAnsible:
    def test_filter_args(self):
        """only diff should be removed"""
        src_cfg = deepcopy(
            CFG_FULL_PULL_DICT.get("ansible", {}).get("pull", {})
        )
        src_cfg.pop("playbook_names")
        out_dict = cc_ansible.filter_args(src_cfg)
        assert out_dict == {
            "url": "https://github/holmanb/vmboot",
            "accept-host-key": True,
            "clean": True,
            "full": True,
            "ssh-common-args": "-y",
            "scp-extra-args": "-l",
            "sftp-extra-args": "-f",
            "checkout": "tree",
            "module-path": "~/.ansible/plugins/modules:"
            "/usr/share/ansible/plugins/modules",
            "timeout": "10",
            "vault-id": "me",
            "connection": "smart",
            "vault-password-file": "/path/to/file",
            "module-name": "git",
            "sleep": "1",
            "tags": "cumulus",
            "skip-tags": "cisco",
            "private-key": "{nope}",
        }

    @mark.parametrize(
        ("cfg_dict", "exception"),
        (
            (CFG_FULL_PULL_DICT, None),
            (CFG_MINIMAL_DICT, None),
            (
                {
                    "ansible": {
                        "package_name": "ansible-core",
                        "install_method": "distro",
                        "pull": {
                            "playbook_names": ["ubuntu.yml"],
                        },
                    }
                },
                ValueError,
            ),
            (
                {
                    "ansible": {
                        "install_method": "pip",
                        "pull": {
                            "url": "https://github/holmanb/vmboot",
                        },
                    }
                },
                ValueError,
            ),
        ),
    )
    def test_required_keys_dict(self, cfg_dict, exception, mocker):
        mocker.patch(M_PATH + "subp.subp", return_value=("", ""))
        mocker.patch(M_PATH + "subp.which", return_value=True)
        mocker.patch(M_PATH + "AnsiblePull.check_deps")
        mocker.patch(
            M_PATH + "AnsiblePull.get_version",
            return_value=cc_ansible.lifecycle.Version(2, 7, 1),
        )
        mocker.patch(
            M_PATH + "AnsiblePullDistro.is_installed",
            return_value=False,
        )
        if exception:
            with raises(exception):
                cc_ansible.handle("", cfg_dict, get_cloud(), [])
        else:
            cloud = get_cloud(mocked_distro=True)
            cloud.distro.pip_package_name = "python3-pip"
            install = cfg_dict["ansible"]["install_method"]
            cc_ansible.handle("", cfg_dict, cloud, [])
            if install == "distro":
                cloud.distro.install_packages.assert_called_once()
                cloud.distro.install_packages.assert_called_with(
                    ["ansible-core"]
                )
            elif install == "pip":
                if HAS_PIP:
                    assert 0 == cloud.distro.install_packages.call_count
                else:
                    cloud.distro.install_packages.assert_called_with(
                        ["python3-pip"]
                    )

    @mark.parametrize(
        ("cfg_list", "exception"),
        (
            (CFG_FULL_PULL_LIST, None),
            (CFG_MINIMAL_LIST, None),
            (
                {
                    "ansible": {
                        "package_name": "ansible-core",
                        "install_method": "distro",
                        "pull": [
                            {
                                "playbook_names": ["ubuntu.yml"],
                            }
                        ],
                    }
                },
                ValueError,
            ),
            (
                {
                    "ansible": {
                        "install_method": "pip",
                        "pull": [
                            {
                                "url": "https://github/holmanb/vmboot",
                            }
                        ],
                    }
                },
                ValueError,
            ),
        ),
    )
    def test_required_keys_list(self, cfg_list, exception, mocker):
        mocker.patch(M_PATH + "subp.subp", return_value=("", ""))
        mocker.patch(M_PATH + "subp.which", return_value=True)
        mocker.patch(M_PATH + "AnsiblePull.check_deps")
        mocker.patch(
            M_PATH + "AnsiblePull.get_version",
            return_value=cc_ansible.lifecycle.Version(2, 7, 1),
        )
        mocker.patch(
            M_PATH + "AnsiblePullDistro.is_installed",
            return_value=False,
        )
        if exception:
            with raises(exception):
                cc_ansible.handle("", cfg_list, get_cloud(), [])
        else:
            cloud = get_cloud(mocked_distro=True)
            cloud.distro.pip_package_name = "python3-pip"
            install = cfg_list["ansible"]["install_method"]
            cc_ansible.handle("", cfg_list, cloud, [])
            if install == "distro":
                cloud.distro.install_packages.assert_called_once()
                cloud.distro.install_packages.assert_called_with(
                    ["ansible-core"]
                )
            elif install == "pip":
                if HAS_PIP:
                    assert 0 == cloud.distro.install_packages.call_count
                else:
                    cloud.distro.install_packages.assert_called_with(
                        ["python3-pip"]
                    )

    @mock.patch(M_PATH + "subp.which", return_value=False)
    def test_deps_not_installed(self, m_which):
        """assert exception raised if package not installed"""
        with raises(ValueError):
            cc_ansible.AnsiblePullDistro(
                get_cloud().distro, "root"
            ).check_deps()

    @mock.patch(M_PATH + "subp.which", return_value=True)
    def test_deps(self, m_which):
        """assert exception not raised if package installed"""
        cc_ansible.AnsiblePullDistro(
            get_cloud().distro, "ansible"
        ).check_deps()

    @mark.serial
    @mock.patch(M_PATH + "subp.subp", return_value=("stdout", "stderr"))
    @mock.patch(M_PATH + "subp.which", return_value=False)
    def test_pip_bootstrap(self, m_which, m_subp):
        distro = get_cloud(mocked_distro=True).distro
        with mock.patch("builtins.__import__", side_effect=ImportError):
            cc_ansible.AnsiblePullPip(distro, "ansible").install("")
        distro.install_packages.assert_called_once()

    @mark.parametrize(
        "mocked_doas_kwargs,expected_result,expected_present_logs,expected_absent_logs",
        [
            (
                {"return_value": ("", "")},
                nullcontext(),
                ["Upgraded pip"],
                ["Failed at upgrading pip"],
            ),
            # When do_as raises a ProcessExecutionError, __upgrade_pip will
            #  catch it then return without raising it
            (
                {"side_effect": ProcessExecutionError()},
                nullcontext(),
                ["Failed at upgrading pip"],
                ["Upgraded pip"],
            ),
            # The below use case is to ensure that the function will raise the
            # error if the error is not ProcessExecutionError (i.e. something
            # went really sideways with do_as and not simply a non-zero exit
            # by the executed command)
            (
                {"side_effect": ZeroDivisionError()},
                raises(ZeroDivisionError),
                [],
                ["Failed at upgrading pip", "Upgraded pip"],
            ),
        ],
    )
    def test_upgrade_pip(
        self,
        mocked_doas_kwargs,
        expected_result,
        expected_present_logs,
        expected_absent_logs,
        caplog,
    ):
        distro = get_cloud(mocked_distro=True).distro
        base_cmd = ["echo", "abc"]
        ansiblePullPip = cc_ansible.AnsiblePullPip(distro, "ansible")
        ansiblePullPip.do_as = MagicMock(**mocked_doas_kwargs)
        with expected_result as e:
            assert ansiblePullPip._AnsiblePullPip__upgrade_pip(base_cmd) == e

            ansiblePullPip.do_as.assert_called_once()
            ansiblePullPip.do_as.assert_called_with(
                [*base_cmd, "--upgrade", "pip"]
            )

            for expected_present_log in expected_present_logs:
                assert expected_present_log in caplog.text

            for expected_absent_log in expected_absent_logs:
                assert expected_absent_log not in caplog.text

    @mock.patch(M_PATH + "subp.which", return_value=True)
    @mock.patch(M_PATH + "subp.subp", return_value=(distro_version, "stderr"))
    @mock.patch(
        "cloudinit.distros.subp.subp", return_value=(distro_version, "stderr")
    )
    @mark.parametrize(
        ("cfg_dict", "expected"),
        (
            (
                CFG_FULL_PULL_DICT,
                [
                    "ansible-pull",
                    "--url=https://github/holmanb/vmboot",
                    "--accept-host-key",
                    "--clean",
                    "--full",
                    "--ssh-common-args=-y",
                    "--scp-extra-args=-l",
                    "--sftp-extra-args=-f",
                    "--checkout=tree",
                    "--module-path=~/.ansible/plugins/modules"
                    ":/usr/share/ansible/plugins/modules",
                    "--timeout=10",
                    "--vault-id=me",
                    "--connection=smart",
                    "--vault-password-file=/path/to/file",
                    "--module-name=git",
                    "--sleep=1",
                    "--tags=cumulus",
                    "--skip-tags=cisco",
                    "--private-key={nope}",
                    "arch.yml",
                ],
            ),
            (
                CFG_MINIMAL_DICT,
                [
                    "ansible-pull",
                    "--url=https://github/holmanb/vmboot",
                    "ubuntu.yml",
                ],
            ),
        ),
    )
    def test_ansible_pull_dict(
        self, m_subp1, m_subp2, m_which, cfg_dict, expected
    ):
        """verify expected ansible invocation from userdata config"""
        pull_type = cfg_dict["ansible"]["install_method"]
        distro = get_cloud().distro
        distro.do_as = MagicMock(return_value=(distro_version, ""))

        ansible_pull = (
            cc_ansible.AnsiblePullPip(distro, "ansible")
            if pull_type == "pip"
            else cc_ansible.AnsiblePullDistro(distro, "")
        )
        cc_ansible.run_ansible_pull(
            ansible_pull, deepcopy(cfg_dict["ansible"]["pull"])
        )

        if pull_type != "pip":
            assert m_subp2.call_args[0][0] == expected
            assert m_subp2.call_args[1]["update_env"].get(
                "HOME"
            ) == os.environ.get("HOME", "/root")

    @mock.patch(M_PATH + "subp.which", return_value=True)
    @mock.patch(M_PATH + "subp.subp", return_value=(distro_version, ""))
    @mock.patch(
        "cloudinit.distros.subp.subp", return_value=(distro_version, "")
    )
    @mark.parametrize(
        ("cfg_list", "expected"),
        (
            (
                CFG_FULL_PULL_LIST,
                [
                    "ansible-pull",
                    "--url=https://github/holmanb/vmboot",
                    "--accept-host-key",
                    "--clean",
                    "--full",
                    "--ssh-common-args=-y",
                    "--scp-extra-args=-l",
                    "--sftp-extra-args=-f",
                    "--checkout=tree",
                    "--module-path=~/.ansible/plugins/modules"
                    ":/usr/share/ansible/plugins/modules",
                    "--timeout=10",
                    "--vault-id=me",
                    "--connection=smart",
                    "--vault-password-file=/path/to/file",
                    "--module-name=git",
                    "--sleep=1",
                    "--tags=cumulus",
                    "--skip-tags=cisco",
                    "--private-key={nope}",
                    "arch.yml",
                ],
            ),
            (
                CFG_MINIMAL_LIST,
                [
                    "ansible-pull",
                    "--url=https://github/holmanb/vmboot",
                    "ubuntu.yml",
                ],
            ),
        ),
    )
    def test_ansible_pull_list(
        self, m_subp1, m_subp2, m_which, cfg_list, expected
    ):
        """verify expected ansible invocation from userdata config"""
        pull_type = cfg_list["ansible"]["install_method"]
        distro = get_cloud().distro
        distro.do_as = MagicMock(return_value=(distro_version, ""))
        ansible_pull = (
            cc_ansible.AnsiblePullPip(distro, "ansible")
            if pull_type == "pip"
            else cc_ansible.AnsiblePullDistro(distro, "")
        )
        for cfg in cfg_list["ansible"]["pull"]:
            cc_ansible.run_ansible_pull(ansible_pull, deepcopy(cfg))

        if pull_type != "pip":
            assert m_subp2.call_args[0][0] == expected
            assert m_subp2.call_args[1]["update_env"].get(
                "HOME"
            ) == os.environ.get("HOME", "/root")

    @mock.patch(M_PATH + "validate_config")
    def test_do_not_run(self, m_validate):
        """verify that if ansible key not included, don't do anything"""
        cc_ansible.handle("", {}, get_cloud(), [])
        assert not m_validate.called

    @mock.patch(
        "cloudinit.config.cc_ansible.subp.subp",
        side_effect=[(distro_version, "")],
    )
    def test_parse_version_distro(self, m_subp):
        """Verify that the expected version is returned"""
        assert cc_ansible.AnsiblePullDistro(
            get_cloud().distro, ""
        ).get_version() == lifecycle.Version(2, 10, 8)

    @mock.patch("cloudinit.subp.subp", side_effect=[(pip_version, "")])
    def test_parse_version_pip(self, m_subp):
        """Verify that the expected version is returned"""
        distro = get_cloud().distro
        distro.do_as = MagicMock(return_value=(pip_version, ""))
        pip = cc_ansible.AnsiblePullPip(distro, "root")
        received = pip.get_version()
        expected = lifecycle.Version(2, 13, 2)
        assert received == expected

    @mock.patch(
        M_PATH + "subp.subp",
        side_effect=[("out", "err"), (distro_version, ""), ("out", "err")],
    )
    @mock.patch(M_PATH + "subp.which", return_value=True)
    def test_ansible_env_var(self, m_which, m_subp):
        cc_ansible.handle("", CFG_FULL_PULL_DICT, get_cloud(), [])

        # python 3.8 required for Mock.call_args.kwargs dict attribute
        if isinstance(m_subp.call_args.kwargs, dict):
            assert (
                "/etc/ansible/ansible.cfg"
                == m_subp.call_args.kwargs["update_env"]["ansible_config"]
            )
