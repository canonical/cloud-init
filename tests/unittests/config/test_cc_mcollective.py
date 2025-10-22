# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
from io import BytesIO

import configobj
import pytest

from cloudinit import util
from cloudinit.config import cc_mcollective
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests import helpers as t_help
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


STOCK_CONFIG = """\
main_collective = mcollective
collectives = mcollective
libdir = /usr/share/mcollective/plugins
logfile = /var/log/mcollective.log
loglevel = info
daemonize = 1

# Plugins
securityprovider = psk
plugin.psk = unset

connector = activemq
plugin.activemq.pool.size = 1
plugin.activemq.pool.1.host = stomp1
plugin.activemq.pool.1.port = 61613
plugin.activemq.pool.1.user = mcollective
plugin.activemq.pool.1.password = marionette

# Facts
factsource = yaml
plugin.yaml = /etc/mcollective/facts.yaml
"""


@pytest.fixture
def server_cfg(tmp_path):
    return str(tmp_path / cc_mcollective.SERVER_CFG)


@pytest.fixture
def pricert_file(tmp_path):
    return str(tmp_path / cc_mcollective.PRICERT_FILE)


@pytest.fixture
def pubcert_file(tmp_path):
    return str(tmp_path / cc_mcollective.PUBCERT_FILE)


@pytest.mark.usefixtures("fake_filesystem")
class TestConfig:
    def test_basic_config(self):
        cfg = {
            "mcollective": {
                "conf": {
                    "loglevel": "debug",
                    "connector": "rabbitmq",
                    "logfile": "/var/log/mcollective.log",
                    "ttl": "4294957",
                    "collectives": "mcollective",
                    "main_collective": "mcollective",
                    "securityprovider": "psk",
                    "daemonize": "1",
                    "factsource": "yaml",
                    "direct_addressing": "1",
                    "plugin.psk": "unset",
                    "libdir": "/usr/share/mcollective/plugins",
                    "identity": "1",
                },
            },
        }
        expected = cfg["mcollective"]["conf"]

        cc_mcollective.configure(cfg["mcollective"]["conf"])
        contents = util.load_binary_file(cc_mcollective.SERVER_CFG)
        contents = configobj.ConfigObj(BytesIO(contents))
        assert expected == dict(contents)

    def test_existing_config_is_saved(self, server_cfg):
        cfg = {"loglevel": "warn"}
        util.write_file(server_cfg, STOCK_CONFIG)
        cc_mcollective.configure(config=cfg, server_cfg=server_cfg)
        assert os.path.exists(server_cfg)
        assert os.path.exists(server_cfg + ".old")
        assert util.load_text_file(server_cfg + ".old") == STOCK_CONFIG

    def test_existing_updated(self, server_cfg):
        cfg = {"loglevel": "warn"}
        util.write_file(server_cfg, STOCK_CONFIG)
        cc_mcollective.configure(config=cfg, server_cfg=server_cfg)
        cfgobj = configobj.ConfigObj(server_cfg)
        assert cfg["loglevel"] == cfgobj["loglevel"]

    def test_certificats_written(self, pricert_file, pubcert_file, server_cfg):
        # check public-cert and private-cert keys in config get written
        cfg = {
            "loglevel": "debug",
            "public-cert": "this is my public-certificate",
            "private-cert": "secret private certificate",
        }

        cc_mcollective.configure(
            config=cfg,
            server_cfg=server_cfg,
            pricert_file=pricert_file,
            pubcert_file=pubcert_file,
        )

        found = configobj.ConfigObj(server_cfg)

        # make sure these didnt get written in
        assert "public-cert" not in found
        assert "private-cert" not in found

        # these need updating to the specified paths
        assert found["plugin.ssl_server_public"] == pubcert_file
        assert found["plugin.ssl_server_private"] == pricert_file

        # and the security provider should be ssl
        assert found["securityprovider"] == "ssl"

        assert util.load_text_file(pricert_file) == cfg["private-cert"]
        assert util.load_text_file(pubcert_file) == cfg["public-cert"]


class TestHandler:
    @t_help.mock.patch("cloudinit.config.cc_mcollective.subp")
    @t_help.mock.patch("cloudinit.config.cc_mcollective.util")
    def test_mcollective_install(self, mock_util, mock_subp):
        cc = get_cloud()
        cc.distro = t_help.mock.MagicMock()
        mock_util.load_binary_file.return_value = b""
        mycfg = {"mcollective": {"conf": {"loglevel": "debug"}}}
        cc_mcollective.handle("cc_mcollective", mycfg, cc, [])
        assert cc.distro.install_packages.called is True
        install_pkg = cc.distro.install_packages.call_args_list[0][0][0]
        assert install_pkg == ["mcollective"]

        assert mock_subp.subp.called is True
        assert mock_subp.subp.call_args_list[0][0][0] == [
            "service",
            "mcollective",
            "restart",
        ]


class TestMcollectiveSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Disallow undocumented keys client 'mcollective' without error
            (
                {"mcollective": {"customkey": True}},
                "mcollective: Additional properties are not allowed",
            ),
            # Allow undocumented keys client keys below 'conf' without error
            ({"mcollective": {"conf": {"customkey": 1}}}, None),
            # Don't allow undocumented keys that don't match expected type
            (
                {"mcollective": {"conf": {"": {"test": None}}}},
                "does not match any of the regexes:",
            ),
            (
                {"mcollective": {"conf": {"public-cert": 1}}},
                "mcollective.conf.public-cert: 1 is not of type 'string'",
            ),
        ],
    )
    @t_help.skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
