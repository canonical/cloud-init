# This file is part of cloud-init. See LICENSE file for license information.

import copy
import os
import re

import pytest

from cloudinit import util
from cloudinit.config import cc_apt_configure


@pytest.fixture
def p_c_files(tmp_path):
    pfile = str(tmp_path / "proxy.cfg")
    cfile = str(tmp_path / "config.cfg")
    return pfile, cfile


def _search_apt_config(contents, ptype, value):
    return re.search(
        r"acquire::%s::proxy\s+[\"']%s[\"'];\n" % (ptype, value),
        contents,
        flags=re.IGNORECASE,
    )


class TestAptProxyConfig:
    @pytest.mark.parametrize(
        "cfg", [{"proxy": "myproxy"}, {"http_proxy": "myproxy"}]
    )
    def test_apt_proxy_written_variants(self, p_c_files, cfg):
        pfile, cfile = p_c_files
        cc_apt_configure.apply_apt_config(cfg, pfile, cfile)

        assert os.path.isfile(pfile)
        assert not os.path.isfile(cfile)

        contents = util.load_text_file(pfile)
        assert _search_apt_config(contents, "http", "myproxy")

    def test_apt_all_proxy_written(self, p_c_files):
        pfile, cfile = p_c_files
        cfg = {
            "http_proxy": "myproxy_http_proxy",
            "https_proxy": "myproxy_https_proxy",
            "ftp_proxy": "myproxy_ftp_proxy",
        }

        values = {
            "http": cfg["http_proxy"],
            "https": cfg["https_proxy"],
            "ftp": cfg["ftp_proxy"],
        }

        cc_apt_configure.apply_apt_config(cfg, pfile, cfile)

        assert os.path.isfile(pfile)
        assert not os.path.isfile(cfile)

        contents = util.load_text_file(pfile)

        for ptype, pval in values.items():
            assert _search_apt_config(contents, ptype, pval)

    def test_proxy_deleted(self, p_c_files):
        pfile, cfile = p_c_files
        util.write_file(cfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({}, pfile, cfile)
        assert not os.path.isfile(pfile)
        assert not os.path.isfile(cfile)

    def test_proxy_replaced(self, p_c_files):
        pfile, cfile = p_c_files
        util.write_file(cfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({"proxy": "foo"}, pfile, cfile)
        assert os.path.isfile(pfile)
        contents = util.load_text_file(pfile)
        assert _search_apt_config(contents, "http", "foo")

    def test_config_written(self, p_c_files):
        pfile, cfile = p_c_files
        payload = "this is my apt config"
        cfg = {"conf": payload}

        cc_apt_configure.apply_apt_config(cfg, pfile, cfile)

        assert os.path.isfile(cfile)
        assert not os.path.isfile(pfile)

        assert util.load_text_file(cfile) == payload

    def test_config_replaced(self, p_c_files):
        pfile, cfile = p_c_files
        util.write_file(pfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({"conf": "foo"}, pfile, cfile)
        assert os.path.isfile(cfile)
        assert util.load_text_file(cfile) == "foo"

    def test_config_deleted(self, p_c_files):
        # if no 'conf' is provided, delete any previously written file
        pfile, cfile = p_c_files
        util.write_file(pfile, "content doesnt matter")
        cc_apt_configure.apply_apt_config({}, pfile, cfile)
        assert not os.path.isfile(pfile)
        assert not os.path.isfile(cfile)


class TestConversion:
    def test_convert_with_apt_mirror_as_empty_string(self):
        # an empty apt_mirror is the same as no apt_mirror
        empty_m_found = cc_apt_configure.convert_to_v3_apt_format(
            {"apt_mirror": ""}
        )
        default_found = cc_apt_configure.convert_to_v3_apt_format({})
        assert default_found == empty_m_found

    def test_convert_with_apt_mirror(self):
        mirror = "http://my.mirror/ubuntu"
        f = cc_apt_configure.convert_to_v3_apt_format({"apt_mirror": mirror})
        assert mirror in set(m["uri"] for m in f["apt"]["primary"])

    def test_no_old_content(self):
        mirror = "http://my.mirror/ubuntu"
        mydata = {"apt": {"primary": {"arches": ["default"], "uri": mirror}}}
        expected = copy.deepcopy(mydata)
        assert expected == cc_apt_configure.convert_to_v3_apt_format(mydata)
