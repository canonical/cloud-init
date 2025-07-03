# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import re
import shutil

import pytest

from cloudinit import cloud, distros, helpers, util
from cloudinit.config import cc_update_etc_hosts
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.helpers import cloud_init_project_dir
from tests.unittests import helpers as t_help

LOG = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def with_templates(tmp_path, fake_filesystem_hook):
    shutil.copytree(
        str(cloud_init_project_dir("templates")),
        str(tmp_path / "templates"),
        dirs_exist_ok=True,
    )


@pytest.mark.usefixtures("fake_filesystem")
class TestHostsFile:
    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({})
        return cls(kind, {}, paths)

    def test_write_etc_hosts_suse_localhost(self, tmp_path):
        cfg = {
            "manage_etc_hosts": "localhost",
            "hostname": "cloud-init.test.us",
        }
        os.makedirs(tmp_path / "etc/")
        hosts_content = "192.168.1.1 blah.blah.us blah\n"
        etc_hosts = str(tmp_path / "etc/hosts")
        fout = open(etc_hosts, "w")
        fout.write(hosts_content)
        fout.close()
        distro = self._fetch_distro("sles")
        distro.hosts_fn = etc_hosts
        paths = helpers.Paths({})
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        cc_update_etc_hosts.handle("test", cfg, cc, [])
        contents = util.load_text_file(etc_hosts)
        assert (
            "127.0.1.1\tcloud-init.test.us\tcloud-init" in contents
        ), "No entry for 127.0.1.1 in etc/hosts"
        assert (
            "192.168.1.1\tblah.blah.us\tblah" in contents
        ), "Default etc/hosts content modified"

    @t_help.skipUnlessJinja()
    def test_write_etc_hosts_suse_template(self, tmp_path):
        cfg = {
            "manage_etc_hosts": "template",
            "hostname": "cloud-init.test.us",
        }
        shutil.copytree(
            tmp_path / "templates", str(tmp_path / "etc/cloud/templates")
        )
        distro = self._fetch_distro("sles")
        paths = helpers.Paths({})
        paths.template_tpl = str(tmp_path / "etc/cloud/templates/%s.tmpl")
        ds = None
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        cc_update_etc_hosts.handle("test", cfg, cc, [])
        contents = util.load_text_file(tmp_path / "etc/hosts")
        assert (
            "127.0.1.1 cloud-init.test.us cloud-init" in contents
        ), "No entry for 127.0.1.1 in etc/hosts"
        assert (
            "::1 cloud-init.test.us cloud-init" in contents
        ), "No entry for 127.0.0.1 in etc/hosts"


class TestUpdateEtcHosts:
    @pytest.mark.parametrize(
        "config, expectation",
        [
            ({"manage_etc_hosts": True}, t_help.does_not_raise()),
            ({"manage_etc_hosts": False}, t_help.does_not_raise()),
            ({"manage_etc_hosts": "localhost"}, t_help.does_not_raise()),
            (
                {"manage_etc_hosts": "template"},
                pytest.raises(
                    SchemaValidationError,
                    match=re.escape(
                        "Cloud config schema deprecations: "
                        "manage_etc_hosts:  Changed in version 22.3. "
                        "Use of **template** is deprecated, use "
                        "``true`` instead."
                    ),
                ),
            ),
            (
                {"manage_etc_hosts": "templatey"},
                pytest.raises(
                    SchemaValidationError,
                    match=re.escape(
                        "manage_etc_hosts: 'templatey' is not one of"
                        " ['template']",
                    ),
                ),
            ),
        ],
    )
    @t_help.skipUnlessJsonSchema()
    def test_schema_validation(self, config, expectation):
        with expectation:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
