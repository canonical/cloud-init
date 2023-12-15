from functools import partial
from itertools import count
from unittest import mock

import pytest

from cloudinit.config.cc_phone_home import POST_LIST_ALL, handle
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

phone_home = partial(handle, name="test", cloud=get_cloud(), args=[])


@pytest.fixture(autouse=True)
def common_mocks(mocker):
    mocker.patch("cloudinit.util.load_file", side_effect=count())


@mock.patch("cloudinit.url_helper.readurl")
class TestPhoneHome:
    def test_default_call(self, m_readurl):
        cfg = {"phone_home": {"url": "myurl"}}
        phone_home(cfg=cfg)
        assert m_readurl.call_args == mock.call(
            "myurl",
            data={
                "pub_key_rsa": "0",
                "pub_key_ecdsa": "1",
                "pub_key_ed25519": "2",
                "instance_id": "iid-datasource-none",
                "hostname": "hostname",
                "fqdn": "hostname",
            },
            retries=9,
            sec_between=3,
            ssl_details={},
        )

    def test_no_url(self, m_readurl, caplog):
        cfg = {"phone_home": {}}
        phone_home(cfg=cfg)
        assert "Skipping module named" in caplog.text
        assert m_readurl.call_count == 0

    @pytest.mark.parametrize(
        "tries, expected_retries",
        [
            (-1, -2),
            (0, -1),
            (1, 0),
            (2, 1),
            ("2", 1),
            ("two", 9),
            (None, 9),
            ({}, 9),
        ],
    )
    def test_tries(self, m_readurl, tries, expected_retries, caplog):
        cfg = {"phone_home": {"url": "dontcare"}}
        if tries is not None:
            cfg["phone_home"]["tries"] = tries
        phone_home(cfg=cfg)
        assert m_readurl.call_args[1]["retries"] == expected_retries

    def test_post_all(self, m_readurl):
        cfg = {"phone_home": {"url": "test", "post": "all"}}
        phone_home(cfg=cfg)
        for key in POST_LIST_ALL:
            assert key in m_readurl.call_args[1]["data"]

    def test_custom_post_list(self, m_readurl):
        post_list = ["pub_key_rsa, hostname"]
        cfg = {"phone_home": {"url": "test", "post": post_list}}
        phone_home(cfg=cfg)
        for key in post_list:
            assert key in m_readurl.call_args[1]["data"]
        assert len(m_readurl.call_args[1]["data"]) == len(post_list)

    def test_invalid_post(self, m_readurl, caplog):
        post_list = ["spam", "hostname"]
        cfg = {"phone_home": {"url": "test", "post": post_list}}
        phone_home(cfg=cfg)
        assert "hostname" in m_readurl.call_args[1]["data"]
        assert m_readurl.call_args[1]["data"]["spam"] == "N/A"
        assert (
            "spam from 'post' configuration list not available" in caplog.text
        )


class TestPhoneHomeSchema:
    @pytest.mark.parametrize(
        "config",
        [
            # phone_home definition with url
            {"phone_home": {"post": ["pub_key_rsa"]}},
            # post using string other than "all"
            {"phone_home": {"url": "test_url", "post": "pub_key_rsa"}},
            # post using list with misspelled entry
            {"phone_home": {"url": "test_url", "post": ["pub_kye_rsa"]}},
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config):
        with pytest.raises(SchemaValidationError):
            validate_cloudconfig_schema(config, get_schema(), strict=True)
