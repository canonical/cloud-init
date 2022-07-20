from logging import getLogger
from unittest import mock

from pytest import mark, param, raises

from cloudinit.config import cc_ansible
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

CFG_FULL = {
    "ansible": {
        "install": True,
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
        "install": True,
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
                        "install": True,
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
                        "install": "true",
                        "pull": {
                            "url": "https://github/holmanb/vmboot",
                            "playbook-name": "debian.yml",
                        },
                    }
                },
                "'true' is not of type 'boolean'",
                id="install-type",
            ),
            param(
                {
                    "ansible": {
                        "install": True,
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
                        "install": True,
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
            with raises(SchemaValidationError, match=error_msg):
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
                        "install": False,
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
                        "install": True,
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
        mocker.patch(
            "cloudinit.config.cc_ansible.subp", return_value=(None, None)
        )
        mocker.patch("cloudinit.config.cc_ansible.which", return_value=True)
        if exception:
            with raises(exception):
                cc_ansible.handle("", cfg, None, None, None)  # pyright: ignore
        else:
            cloud = get_cloud(mocked_distro=True)
            install = cfg["ansible"]["install"]
            cc_ansible.handle("", cfg, cloud, getLogger(), None)
            if install:
                cloud.distro.install_packages.assert_called_once()
                cloud.distro.install_packages.assert_called_with("ansible")

    @mock.patch("cloudinit.config.cc_ansible.which", return_value=False)
    def test_deps_not_installed(self, m_which):
        with raises(ValueError):
            cc_ansible.check_deps("ansible")

    @mock.patch("cloudinit.config.cc_ansible.which", return_value=True)
    def test_deps(self, m_which):
        cc_ansible.check_deps("ansible")

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
                    "--playbook-name=arch.yml",
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
                    "--playbook-name=ubuntu.yml",
                    "ubuntu.yml",
                ],
            ),
        ),
    )
    def test_ansible_pull(self, m_subp, m_which, cfg, expected):
        cc_ansible.run_ansible_pull(cfg["ansible"]["pull"], getLogger())
        m_subp.assert_called_with(expected)

    @mock.patch("cloudinit.config.cc_ansible.get_and_validate_config")
    def test_do_not_run(self, m_validate):
        cc_ansible.handle("", {}, None, None, None)  # pyright: ignore
        assert not m_validate.called
