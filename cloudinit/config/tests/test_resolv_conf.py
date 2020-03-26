from unittest import mock

import pytest

from cloudinit.config.cc_resolv_conf import generate_resolv_conf


EXPECTED_HEADER = """\
# Your system has been configured with 'manage-resolv-conf' set to true.
# As a result, cloud-init has written this file with configuration data
# that it has been provided. Cloud-init, by default, will write this file
# a single time (PER_ONCE).
#\n\n"""


class TestGenerateResolvConf:
    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_default_target_fname_is_etc_resolvconf(self, m_render_to_file):
        generate_resolv_conf("templates/resolv.conf.tmpl", mock.MagicMock())

        assert [
            mock.call(mock.ANY, "/etc/resolv.conf", mock.ANY)
        ] == m_render_to_file.call_args_list

    @mock.patch("cloudinit.config.cc_resolv_conf.templater.render_to_file")
    def test_target_fname_is_used_if_passed(self, m_render_to_file):
        generate_resolv_conf(
            "templates/resolv.conf.tmpl", mock.MagicMock(), "/use/this/path"
        )

        assert [
            mock.call(mock.ANY, "/use/this/path", mock.ANY)
        ] == m_render_to_file.call_args_list

    # Patch in templater so we can assert on the actual generated content
    @mock.patch("cloudinit.templater.util.write_file")
    # Parameterise with the value to be passed to generate_resolv_conf as the
    # `params` parameter, and a list of the expected lines after the header as
    # `extra_lines`.
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
        generate_resolv_conf("templates/resolv.conf.tmpl", params)

        expected_content = EXPECTED_HEADER
        if expected_extra_line is not None:
            # If we have any extra lines, expect a trailing newline
            expected_content += "\n".join([expected_extra_line, ""])
        assert [
            mock.call(mock.ANY, expected_content, mode=mock.ANY)
        ] == m_write_file.call_args_list
