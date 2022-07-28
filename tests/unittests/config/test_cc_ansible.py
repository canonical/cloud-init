import re
from copy import deepcopy
from logging import getLogger
from textwrap import dedent
from unittest import mock
from unittest.mock import call

from pytest import mark, param, raises

from cloudinit import util
from cloudinit.config import cc_ansible
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

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

CFG_FULL = {
    "ansible": {
        "install-method": "distro",
        "package-name": "ansible-core",
        "pull": {
            "url": "https://github/holmanb/vmboot",
            "playbook-name": "arch.yml",
            "accept-host-key": True,
            "clean": True,
            "full": True,
            "diff": False,
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
        },
    }
}
CFG_MINIMAL = {
    "ansible": {
        "install-method": "pip",
        "package-name": "ansible",
        "pull": {
            "url": "https://github/holmanb/vmboot",
            "playbook-name": "ubuntu.yml",
        },
    }
}


class TestSetPasswordsSchema:
    @mark.parametrize(
        ("config", "error_msg"),
        (
            param(
                CFG_MINIMAL,
                None,
                id="essentials",
            ),
            param(
                {
                    "ansible": {
                        "install-method": "distro",
                        "pull": {
                            "url": "https://github/holmanb/vmboot",
                            "playbook-name": "centos.yml",
                            "dance": "bossa nova",
                        },
                    }
                },
                "Additional properties are not allowed ",
                id="additional-properties",
            ),
            param(
                CFG_FULL,
                None,
                id="all-keys",
            ),
            param(
                {
                    "ansible": {
                        "install-method": "true",
                        "pull": {
                            "url": "https://github/holmanb/vmboot",
                            "playbook-name": "debian.yml",
                        },
                    }
                },
                "'true' is not one of ['distro', 'pip']",
                id="install-type",
            ),
            param(
                {
                    "ansible": {
                        "install-method": "pip",
                        "pull": {
                            "playbook-name": "fedora.yml",
                        },
                    }
                },
                "'url' is a required property",
                id="require-url",
            ),
            param(
                {
                    "ansible": {
                        "install-method": "pip",
                        "pull": {
                            "url": "gophers://encrypted-gophers/",
                        },
                    }
                },
                "'playbook-name' is a required property",
                id="require-url",
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
        out = cc_ansible.filter_args(
            CFG_FULL.get("ansible", {}).get("pull", {})
        )
        assert out == {
            "url": "https://github/holmanb/vmboot",
            "playbook-name": "arch.yml",
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
        ("cfg", "exception"),
        (
            (CFG_FULL, None),
            (CFG_MINIMAL, None),
            (
                {
                    "ansible": {
                        "package-name": "ansible-core",
                        "install-method": "distro",
                        "pull": {
                            "playbook-name": "ubuntu.yml",
                        },
                    }
                },
                ValueError,
            ),
            (
                {
                    "ansible": {
                        "install-method": "pip",
                        "pull": {
                            "url": "https://github/holmanb/vmboot",
                        },
                    }
                },
                ValueError,
            ),
        ),
    )
    def test_required_keys(self, cfg, exception, mocker):
        m_subp = mocker.patch(
            "cloudinit.config.cc_ansible.subp", return_value=("", "")
        )
        mocker.patch("cloudinit.config.cc_ansible.which", return_value=True)
        mocker.patch(
            "cloudinit.config.cc_ansible.AnsiblePull.get_version",
            return_value=cc_ansible.Version(2, 7, 1),
        )
        mocker.patch("cloudinit.config.cc_ansible.AnsiblePull.check_deps")
        mocker.patch(
            "cloudinit.config.cc_ansible.AnsiblePullDistro.is_installed",
            return_value=False,
        )
        if exception:
            with raises(exception):
                cc_ansible.handle("", cfg, get_cloud(), None, None)
        else:
            cloud = get_cloud(mocked_distro=True)
            print(cfg)
            install = cfg["ansible"]["install-method"]
            cc_ansible.handle("", cfg, cloud, getLogger(), None)
            if install == "distro":
                cloud.distro.install_packages.assert_called_once()
                cloud.distro.install_packages.assert_called_with(
                    "ansible-core"
                )
            elif install == "pip":
                m_subp.assert_has_calls(
                    [
                        call(["python3", "-m", "pip", "list"]),
                        call(
                            [
                                "python3",
                                "-m",
                                "pip",
                                "install",
                                "--user",
                                "ansible",
                            ]
                        ),
                    ]
                )
                assert m_subp.call_args[0][0] == [
                    "ansible-pull",
                    "--url=https://github/holmanb/vmboot",
                    "ubuntu.yml",
                ]

    @mock.patch("cloudinit.config.cc_ansible.which", return_value=False)
    def test_deps_not_installed(self, m_which):
        with raises(ValueError):
            cc_ansible.AnsiblePullDistro(get_cloud().distro).check_deps()

    @mock.patch("cloudinit.config.cc_ansible.which", return_value=True)
    def test_deps(self, m_which):
        cc_ansible.AnsiblePullDistro(get_cloud().distro).check_deps()

    @mock.patch("cloudinit.config.cc_ansible.which", return_value=True)
    @mock.patch(
        "cloudinit.config.cc_ansible.subp", return_value=("stdout", "stderr")
    )
    @mark.parametrize(
        ("cfg", "expected"),
        (
            (
                CFG_FULL,
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
                CFG_MINIMAL,
                [
                    "ansible-pull",
                    "--url=https://github/holmanb/vmboot",
                    "ubuntu.yml",
                ],
            ),
        ),
    )
    def test_ansible_pull(self, m_subp, m_which, cfg, expected):
        pull_type = cfg["ansible"]["install-method"]
        ansible_pull = (
            cc_ansible.AnsiblePullPip()
            if pull_type == "pip"
            else cc_ansible.AnsiblePullDistro(get_cloud().distro)
        )
        cc_ansible.run_ansible_pull(
            ansible_pull, deepcopy(cfg["ansible"]["pull"]), getLogger()
        )
        assert m_subp.call_args[0][0] == expected

    @mock.patch("cloudinit.config.cc_ansible.validate_config")
    def test_do_not_run(self, m_validate):
        cc_ansible.handle("", {}, None, None, None)  # pyright: ignore
        assert not m_validate.called

    @mock.patch(
        "cloudinit.config.cc_ansible.subp",
        side_effect=[
            (distro_version, ""),
            (pip_version, ""),
            (" ansible 2.1.0", ""),
            (" ansible 2.1.0", ""),
        ],
    )
    def test_parse_version(self, m_subp):
        assert cc_ansible.AnsiblePullDistro(
            get_cloud().distro
        ).get_version() == cc_ansible.Version(2, 10, 8)
        assert cc_ansible.AnsiblePullPip().get_version() == cc_ansible.Version(
            2, 13, 2
        )

        assert util.Version(2, 1, 0, -1) == cc_ansible.AnsiblePullPip().get_version()
        assert util.Version(2, 1, 0, -1) == cc_ansible.AnsiblePullDistro(get_cloud().distro).get_version()
