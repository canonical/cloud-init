# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import shutil
import tempfile
from copy import deepcopy
from unittest import mock

import pytest

from cloudinit import cloud, distros, helpers, util
from cloudinit.config import cc_resolv_conf
from cloudinit.config.cc_resolv_conf import generate_resolv_conf
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.helpers import cloud_init_project_dir
from tests.unittests.helpers import (
    FilesystemMockingTestCase,
    skipUnlessJsonSchema,
)
from tests.unittests.util import MockDistro

LOG = logging.getLogger(__name__)
EXPECTED_HEADER = """\
# Your system has been configured with 'manage-resolv-conf' set to true.
# As a result, cloud-init has written this file with configuration data
# that it has been provided. Cloud-init, by default, will write this file
# a single time (PER_ONCE).
#\n\n"""


class TestResolvConf(FilesystemMockingTestCase):
    with_logs = True
    cfg = {"manage_resolv_conf": True, "resolv_conf": {}}

    def setUp(self):
        super(TestResolvConf, self).setUp()
        self.tmp = tempfile.mkdtemp()
        util.ensure_dir(os.path.join(self.tmp, "data"))
        self.addCleanup(shutil.rmtree, self.tmp)

    def _fetch_distro(self, kind, conf=None):
        cls = distros.fetch(kind)
        paths = helpers.Paths({"cloud_dir": self.tmp})
        conf = {} if conf is None else conf
        return cls(kind, conf, paths)

    def call_resolv_conf_handler(self, distro_name, conf, cc=None):
        if not cc:
            ds = None
            distro = self._fetch_distro(distro_name, conf)
            paths = helpers.Paths({"cloud_dir": self.tmp})
            cc = cloud.Cloud(ds, paths, {}, distro, None)
        cc_resolv_conf.handle("cc_resolv_conf", conf, cc, [])

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_resolv_conf_systemd_resolved(self, m_render_to_file):
        self.call_resolv_conf_handler("photon", self.cfg)

        assert [
            mock.call(mock.ANY, "/etc/systemd/resolved.conf", mock.ANY)
        ] == m_render_to_file.call_args_list

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_resolv_conf_no_param(self, m_render_to_file):
        tmp = deepcopy(self.cfg)
        self.logs.truncate(0)
        tmp.pop("resolv_conf")
        self.call_resolv_conf_handler("photon", tmp)

        self.assertIn(
            "manage_resolv_conf True but no parameters provided",
            self.logs.getvalue(),
        )
        assert [
            mock.call(mock.ANY, "/etc/systemd/resolved.conf", mock.ANY)
        ] not in m_render_to_file.call_args_list

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_resolv_conf_manage_resolv_conf_false(self, m_render_to_file):
        tmp = deepcopy(self.cfg)
        self.logs.truncate(0)
        tmp["manage_resolv_conf"] = False
        self.call_resolv_conf_handler("photon", tmp)
        self.assertIn(
            "'manage_resolv_conf' present but set to False",
            self.logs.getvalue(),
        )
        assert [
            mock.call(mock.ANY, "/etc/systemd/resolved.conf", mock.ANY)
        ] not in m_render_to_file.call_args_list

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_resolv_conf_etc_resolv_conf(self, m_render_to_file):
        self.call_resolv_conf_handler("rhel", self.cfg)

        assert [
            mock.call(mock.ANY, "/etc/resolv.conf", mock.ANY)
        ] == m_render_to_file.call_args_list

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_resolv_conf_invalid_resolve_conf_fn(self, m_render_to_file):
        ds = None
        distro = self._fetch_distro("rhel", self.cfg)
        paths = helpers.Paths({"cloud_dir": self.tmp})
        cc = cloud.Cloud(ds, paths, {}, distro, None)
        cc.distro.resolve_conf_fn = "bla"

        self.logs.truncate(0)
        self.call_resolv_conf_handler("rhel", self.cfg, cc)

        self.assertIn(
            "No template found, not rendering resolve configs",
            self.logs.getvalue(),
        )

        assert [
            mock.call(mock.ANY, "/etc/resolv.conf", mock.ANY)
        ] not in m_render_to_file.call_args_list


class TestGenerateResolvConf:

    dist = MockDistro()
    tmpl_fn = cloud_init_project_dir("templates/resolv.conf.tmpl")

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_dist_resolv_conf_fn(self, m_render_to_file):
        self.dist.resolve_conf_fn = "/tmp/resolv-test.conf"
        generate_resolv_conf(
            self.tmpl_fn, mock.MagicMock(), self.dist.resolve_conf_fn
        )

        assert [
            mock.call(mock.ANY, self.dist.resolve_conf_fn, mock.ANY)
        ] == m_render_to_file.call_args_list

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_target_fname_is_used_if_passed(self, m_render_to_file):
        path = "/use/this/path"
        generate_resolv_conf(self.tmpl_fn, mock.MagicMock(), path)

        assert [
            mock.call(mock.ANY, path, mock.ANY)
        ] == m_render_to_file.call_args_list

    # Patch in templater so we can assert on the actual generated content
    @mock.patch("cloudinit.templater.util.write_file")
    # Parameterise with the value to be passed to generate_resolv_conf as the
    # params parameter, and the expected line after the header as
    # expected_extra_line.
    @pytest.mark.parametrize(
        "params,expected_extra_line",
        [
            # No options
            ({}, None),
            # Just a true flag
            ({"options": {"foo": True}}, "options foo"),
            # Just a false flag
            ({"options": {"foo": False}}, None),
            # Just an option
            ({"options": {"foo": "some_value"}}, "options foo:some_value"),
            # A true flag and an option
            (
                {"options": {"foo": "some_value", "bar": True}},
                "options bar foo:some_value",
            ),
            # Two options
            (
                {"options": {"foo": "some_value", "bar": "other_value"}},
                "options bar:other_value foo:some_value",
            ),
            # Everything
            (
                {
                    "options": {
                        "foo": "some_value",
                        "bar": "other_value",
                        "baz": False,
                        "spam": True,
                    }
                },
                "options spam bar:other_value foo:some_value",
            ),
        ],
    )
    def test_flags_and_options(
        self, m_write_file, params, expected_extra_line
    ):
        target_fn = "/etc/resolv.conf"
        generate_resolv_conf(self.tmpl_fn, params, target_fn)

        expected_content = EXPECTED_HEADER
        if expected_extra_line is not None:
            # If we have any extra lines, expect a trailing newline
            expected_content += "\n".join([expected_extra_line, ""])
        assert [
            mock.call(mock.ANY, expected_content, mode=mock.ANY)
        ] == m_write_file.call_args_list


class TestResolvConfSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Valid
            ({"manage_resolv_conf": False}, None),
            ({"resolv_conf": {"options": {"any": "thing"}}}, None),
            # Invalid
            (
                {"manage_resolv_conf": "asdf"},
                "'asdf' is not of type 'boolean'",
            ),
            # What may be some common misunderstandings of the template
            (
                {"resolv_conf": {"nameserver": ["1.1.1.1"]}},
                "Additional properties are not allowed",
            ),
            (
                {"resolv_conf": {"nameservers": "1.1.1.1"}},
                "'1.1.1.1' is not of type 'array'",
            ),
            (
                {"resolv_conf": {"search": ["foo.com"]}},
                "Additional properties are not allowed",
            ),
            (
                {"resolv_conf": {"searchdomains": "foo.com"}},
                "'foo.com' is not of type 'array'",
            ),
            (
                {"resolv_conf": {"domain": ["foo.com"]}},
                r"\['foo.com'\] is not of type 'string'",
            ),
            (
                {"resolv_conf": {"sortlist": "1.2.3.4"}},
                "'1.2.3.4' is not of type 'array'",
            ),
            (
                {"resolv_conf": {"options": "timeout: 1"}},
                "'timeout: 1' is not of type 'object'",
            ),
            (
                {"resolv_conf": {"options": "rotate"}},
                "'rotate' is not of type 'object'",
            ),
            (
                {"resolv_conf": {"options": ["rotate"]}},
                r"\['rotate'\] is not of type 'object'",
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
