# This file is part of cloud-init. See LICENSE file for license information.
from unittest import mock

import pytest

from cloudinit.config import cc_salt_minion
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud


@pytest.fixture(autouse=True)
def common_mocks(mocker):
    mocker.patch("cloudinit.util.ensure_dir")
    mocker.patch("cloudinit.safeyaml.dumps")
    mocker.patch("cloudinit.util.write_file")


@skipUnlessJsonSchema()
class TestSaltMinionSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            ({"salt_minion": {"conf": {"any": "thing"}}}, None),
            ({"salt_minion": {"grains": {"any": "thing"}}}, None),
            (
                {"salt_minion": {"invalid": "key"}},
                "Additional properties are not allowed",
            ),
            ({"salt_minion": {"conf": "a"}}, "'a' is not of type 'object'"),
            ({"salt_minion": {"grains": "a"}}, "'a' is not of type 'object'"),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)


class TestDaemonInstall:
    def test_daemon_install(self, mocker):
        m_subp = mocker.patch("cloudinit.subp.subp")
        m_manage = mocker.patch(
            "tests.unittests.util.MockDistro.manage_service"
        )
        cc_salt_minion.handle(
            name="name", cfg={"salt_minion": {}}, cloud=get_cloud(), args=[]
        )
        assert m_manage.call_args_list == [
            mock.call("enable", "salt-minion"),
            mock.call("restart", "salt-minion"),
        ]
        m_subp.assert_not_called()

    def test_file_client_local(self, mocker):
        m_subp = mocker.patch("cloudinit.subp.subp")
        m_manage = mocker.patch(
            "tests.unittests.util.MockDistro.manage_service"
        )
        cc_salt_minion.handle(
            name="name",
            cfg={
                "salt_minion": {
                    "conf": {
                        "file_client": "local",
                    }
                }
            },
            cloud=get_cloud(),
            args=[],
        )
        assert m_manage.call_args_list == [
            mock.call("disable", "salt-minion"),
            mock.call("stop", "salt-minion"),
        ]

        m_subp.assert_called_once_with(
            ["salt-call", "--local", "state.apply"], capture=False
        )
