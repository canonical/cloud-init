import pytest

from unittest import mock
from cloudinit.config.cc_resolv_conf import generate_resolv_conf
from tests.unittests.test_distros.test_create_users import MyBaseDistro

EXPECTED_HEADER = """\
# Your system has been configured with 'manage-resolv-conf' set to true.
# As a result, cloud-init has written this file with configuration data
# that it has been provided. Cloud-init, by default, will write this file
# a single time (PER_ONCE).
#\n\n"""


class TestGenerateResolvConf:

    dist = MyBaseDistro()
    tmpl_fn = "templates/resolv.conf.tmpl"

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_dist_resolv_conf_fn(self, m_render_to_file):
        self.dist.resolve_conf_fn = "/tmp/resolv-test.conf"
        generate_resolv_conf(self.tmpl_fn,
                             mock.MagicMock(),
                             self.dist.resolve_conf_fn)

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
