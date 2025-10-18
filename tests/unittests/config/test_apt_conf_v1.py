# This file is part of cloud-init. See LICENSE file for license information.

import copy
import os
import re

from cloudinit import util
from cloudinit.config import cc_apt_configure


def _search_apt_config(contents, ptype, value):
    return re.search(
        r"acquire::%s::proxy\s+[\"']%s[\"'];\n" % (ptype, value),
        contents,
        flags=re.IGNORECASE,
    )


class TestAptProxyConfig:
    def test_apt_proxy_written(self, tmpdir):
        pfile = tmpdir.join("proxy.cfg")
        cfile = tmpdir.join("config.cfg")
        cfg = {"proxy": "myproxy"}
        cc_apt_configure.apply_apt_config(cfg, str(pfile), str(cfile))

        assert os.path.isfile(str(pfile))
        assert not os.path.isfile(str(cfile))

        contents = util.load_text_file(str(pfile))
        assert _search_apt_config(contents, "http", "myproxy")

    def test_apt_http_proxy_written(self, tmpdir):
        pfile = tmpdir.join("proxy.cfg")
        cfile = tmpdir.join("config.cfg")
        cfg = {"http_proxy": "myproxy"}
        cc_apt_configure.apply_apt_config(cfg, str(pfile), str(cfile))

        assert os.path.isfile(str(pfile))
        assert not os.path.isfile(str(cfile))

        contents = util.load_text_file(str(pfile))
        assert _search_apt_config(contents, "http", "myproxy")

    def test_apt_all_proxy_written(self, tmpdir):
        pfile = tmpdir.join("proxy.cfg")
        cfile = tmpdir.join("config.cfg")
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

        cc_apt_configure.apply_apt_config(cfg, str(pfile), str(cfile))

        assert os.path.isfile(str(pfile))
        assert not os.path.isfile(str(cfile))

        contents = util.load_text_file(str(pfile))

        for ptype, pval in values.items():
            assert _search_apt_config(contents, ptype, pval)

    def test_proxy_deleted(self, tmpdir):
        pfile = tmpdir.join("proxy.cfg")
        cfile = tmpdir.join("config.cfg")
        util.write_file(str(cfile), "content doesnt matter")
        cc_apt_configure.apply_apt_config({}, str(pfile), str(cfile))
        assert not os.path.isfile(str(pfile))
        assert not os.path.isfile(str(cfile))

    def test_proxy_replaced(self, tmpdir):
        pfile = tmpdir.join("proxy.cfg")
        cfile = tmpdir.join("config.cfg")
        util.write_file(str(cfile), "content doesnt matter")
        cc_apt_configure.apply_apt_config(
            {"proxy": "foo"}, str(pfile), str(cfile)
        )
        assert os.path.isfile(str(pfile))
        contents = util.load_text_file(str(pfile))
        assert _search_apt_config(contents, "http", "foo")

    def test_config_written(self, tmpdir):
        pfile = tmpdir.join("proxy.cfg")
        cfile = tmpdir.join("config.cfg")
        payload = "this is my apt config"
        cfg = {"conf": payload}

        cc_apt_configure.apply_apt_config(cfg, str(pfile), str(cfile))

        assert os.path.isfile(str(cfile))
        assert not os.path.isfile(str(pfile))

        assert util.load_text_file(str(cfile)) == payload

    def test_config_replaced(self, tmpdir):
        pfile = tmpdir.join("proxy.cfg")
        cfile = tmpdir.join("config.cfg")
        util.write_file(str(pfile), "content doesnt matter")
        cc_apt_configure.apply_apt_config(
            {"conf": "foo"}, str(pfile), str(cfile)
        )
        assert os.path.isfile(str(cfile))
        assert util.load_text_file(str(cfile)) == "foo"

    def test_config_deleted(self, tmpdir):
        pfile = tmpdir.join("proxy.cfg")
        cfile = tmpdir.join("config.cfg")
        # if no 'conf' is provided, delete any previously written file
        util.write_file(str(pfile), "content doesnt matter")
        cc_apt_configure.apply_apt_config({}, str(pfile), str(cfile))
        assert not os.path.isfile(str(pfile))
        assert not os.path.isfile(str(cfile))


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
