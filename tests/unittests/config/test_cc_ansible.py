from pytest import mark, param, raises

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema


class TestSetPasswordsSchema:
    @mark.parametrize(
        "config, error_msg",
        [
            param(
                {
                    "ansible": {
                        "install": True,
                        "pull": {
                            "url": "https://fishing.net/",
                            "playbook-name": "hail-mary.yml",
                        },
                    }
                },
                None,
                id="essentials",
            ),
            param(
                {
                    "ansible": {
                        "install": True,
                        "pull": {
                            "url": "http://flash-games.net/",
                            "playbook-name": "hail-mary.yml",
                            "dance": "bossa nova",
                        },
                    }
                },
                "Additional properties are not allowed ",
                id="additional-properties",
            ),
            param(
                {
                    "ansible": {
                        "install": True,
                        "pull": {
                            "url": "https://flash-games.net/",
                            "playbook-name": "hail-mary.yml",
                            "accept-host-key": True,
                            "clean": True,
                            "full": True,
                            "diff": True,
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
                            "private-key": "perhaps a more diverse playbook"
                            "is the key to winning?",
                        },
                    }
                },
                None,
                id="all-keys",
            ),
            param(
                {
                    "ansible": {
                        "install": "true",
                        "pull": {
                            "url": "gophers://encrypted-gophers/",
                            "playbook-name": "hail-mary.yml",
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
                            "playbook-name": "hail-mary.yml",
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
                            "url": "https://soundcloud.com/sangobeats/flor",
                        },
                    }
                },
                "'playbook-name' is a required property",
                id="require-url",
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
