# Copyright (C) 2014 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import textwrap

import pytest

from cloudinit import templater
from cloudinit.templater import JinjaSyntaxParsingException
from cloudinit.util import load_file, write_file
from tests.unittests import helpers as test_helpers


class TestTemplates(test_helpers.CiTestCase):

    with_logs = True

    jinja_utf8 = b"It\xe2\x80\x99s not ascii, {{name}}\n"
    jinja_utf8_rbob = b"It\xe2\x80\x99s not ascii, bob\n".decode("utf-8")

    @staticmethod
    def add_header(renderer, data):
        """Return text (py2 unicode/py3 str) with template header."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return "## template: %s\n" % renderer + data

    def test_render_basic(self):
        in_data = textwrap.dedent(
            """
            ${b}

            c = d
            """
        )
        in_data = in_data.strip()
        expected_data = textwrap.dedent(
            """
            2

            c = d
            """
        )
        out_data = templater.basic_render(in_data, {"b": 2})
        self.assertEqual(expected_data.strip(), out_data)

    def test_render_jinja(self):
        blob = """## template:jinja
{{a}},{{b}}"""
        c = templater.render_string(blob, {"a": 1, "b": 2})
        self.assertEqual("1,2", c)

    def test_render_default(self):
        blob = """$a,$b"""
        c = templater.render_string(blob, {"a": 1, "b": 2})
        self.assertEqual("1,2", c)

    def test_render_basic_deeper(self):
        hn = "myfoohost.yahoo.com"
        expected_data = "h=%s\nc=d\n" % hn
        in_data = "h=$hostname.canonical_name\nc=d\n"
        params = {
            "hostname": {
                "canonical_name": hn,
            },
        }
        out_data = templater.render_string(in_data, params)
        self.assertEqual(expected_data, out_data)

    def test_render_basic_no_parens(self):
        hn = "myfoohost"
        in_data = "h=$hostname\nc=d\n"
        expected_data = "h=%s\nc=d\n" % hn
        out_data = templater.basic_render(in_data, {"hostname": hn})
        self.assertEqual(expected_data, out_data)

    def test_render_basic_parens(self):
        hn = "myfoohost"
        in_data = "h = ${hostname}\nc=d\n"
        expected_data = "h = %s\nc=d\n" % hn
        out_data = templater.basic_render(in_data, {"hostname": hn})
        self.assertEqual(expected_data, out_data)

    def test_render_basic2(self):
        mirror = "mymirror"
        codename = "zany"
        in_data = "deb $mirror $codename-updates main contrib non-free"
        ex_data = "deb %s %s-updates main contrib non-free" % (
            mirror,
            codename,
        )

        out_data = templater.basic_render(
            in_data, {"mirror": mirror, "codename": codename}
        )
        self.assertEqual(ex_data, out_data)

    def test_jinja_nonascii_render_to_string(self):
        """Test jinja render_to_string with non-ascii content."""
        self.assertEqual(
            templater.render_string(
                self.add_header("jinja", self.jinja_utf8), {"name": "bob"}
            ),
            self.jinja_utf8_rbob,
        )

    def test_jinja_nonascii_render_undefined_variables_to_default_py3(self):
        """Test py3 jinja render_to_string with undefined variable default."""
        self.assertEqual(
            templater.render_string(
                self.add_header("jinja", self.jinja_utf8), {}
            ),
            self.jinja_utf8_rbob.replace("bob", "CI_MISSING_JINJA_VAR/name"),
        )

    def test_jinja_nonascii_render_to_file(self):
        """Test jinja render_to_file of a filename with non-ascii content."""
        tmpl_fn = self.tmp_path("j-render-to-file.template")
        out_fn = self.tmp_path("j-render-to-file.out")
        write_file(
            filename=tmpl_fn,
            omode="wb",
            content=self.add_header("jinja", self.jinja_utf8).encode("utf-8"),
        )
        templater.render_to_file(tmpl_fn, out_fn, {"name": "bob"})
        result = load_file(out_fn, decode=False).decode("utf-8")
        self.assertEqual(result, self.jinja_utf8_rbob)

    def test_jinja_nonascii_render_from_file(self):
        """Test jinja render_from_file with non-ascii content."""
        tmpl_fn = self.tmp_path("j-render-from-file.template")
        write_file(
            tmpl_fn,
            omode="wb",
            content=self.add_header("jinja", self.jinja_utf8).encode("utf-8"),
        )
        result = templater.render_from_file(tmpl_fn, {"name": "bob"})
        self.assertEqual(result, self.jinja_utf8_rbob)

    @test_helpers.skipIfJinja()
    def test_jinja_warns_on_missing_dep_and_uses_basic_renderer(self):
        """Test jinja render_from_file will fallback to basic renderer."""
        tmpl_fn = self.tmp_path("j-render-from-file.template")
        write_file(
            tmpl_fn,
            omode="wb",
            content=self.add_header("jinja", self.jinja_utf8).encode("utf-8"),
        )
        result = templater.render_from_file(tmpl_fn, {"name": "bob"})
        self.assertEqual(result, self.jinja_utf8.decode())
        self.assertIn(
            "WARNING: Jinja not available as the selected renderer for desired"
            " template, reverting to the basic renderer.",
            self.logs.getvalue(),
        )

    def test_jinja_do_extension_render_to_string(self):
        """Test jinja render_to_string using do extension."""
        expected_result = "[1, 2, 3]"
        jinja_template = (
            "{% set r = [] %} {% set input = [1,2,3] %} "
            "{% for i in input %} {% do r.append(i) %} {% endfor %} {{r}}"
        )
        self.assertEqual(
            templater.render_string(
                self.add_header("jinja", jinja_template), {}
            ).strip(),
            expected_result,
        )


class TestJinjaSyntaxParsingException:
    def test_jinja_syntax_parsing_exception_message(self):
        """
        Test that the message of the JinjaSyntaxParsingException is written and
        formatted as expected, and that the template is filled in correctly.
        """
        jinja_template = (
            "## template: jinja\n"
            "#cloud-config\n"
            "runcmd:\n"
            "{% if 1 == 1 % }\n"
            '  - echo "1 is equal to 1"\n'
            "{% endif %}\n"
        )
        expected_error_msg = (
            "Unable to parse Jinja template due to syntax error: "
            "unexpected '}' on line 4: {% if 1 == 1 % }"
        )
        with pytest.raises(JinjaSyntaxParsingException) as excinfo:
            templater.render_string(jinja_template, {})
        assert str(excinfo.value) == expected_error_msg

    @pytest.mark.parametrize(
        "line_no,replace_tuple,syntax_error",
        (
            (
                4,
                ("%}", "% }"),
                "unexpected '}'",
            ),
            (
                6,
                ("%}", "% }"),
                "expected token 'end of statement block', got '%'",
            ),
            (
                8,
                ("%}", "% }"),
                "expected token 'end of statement block', got '%'",
            ),
            (
                4,
                ("%}", "}}"),
                "unexpected '}'",
            ),
            (
                6,
                ("%}", "}}"),
                "unexpected '}'",
            ),
            (
                8,
                ("%}", "}}"),
                "unexpected '}'",
            ),
            (
                4,
                ("==", "="),
                "expected token 'end of statement block', got '='",
            ),
            (
                7,
                ("}}", "} }"),
                "unexpected '}'",
            ),
        ),
    )
    def test_functionality_for_various_syntax_errors(
        self, line_no, replace_tuple, syntax_error
    ):
        """
        Test a variety of jinja syntax errors and make sure the exceptions
        are raised with the correct syntax error, line number, and line content
        as expected.
        """
        jinja_template = (
            "## template: jinja\n"
            "#cloud-config\n"
            "runcmd:\n"
            '{% if v1.cloud_name == "unknown" %}\n'
            '  - echo "Cloud name is unknown"\n'
            "{% else %}\n"
            '  - echo "Cloud name is known: {{ v1.cloud_name }}"\n'
            "{% endif %}\n"
        )
        # replace "%}" in line_no with "% }"
        jinja_template = jinja_template.replace(
            jinja_template.split("\n")[line_no - 1],
            jinja_template.split("\n")[line_no - 1].replace(*replace_tuple),
        )

        with pytest.raises(JinjaSyntaxParsingException) as excinfo:
            templater.render_string(jinja_template, {})
        error: JinjaSyntaxParsingException = excinfo.value
        assert error.lineno == line_no
        assert error.message == syntax_error
        assert (
            error.source.splitlines()[line_no - 2]  # -2 because of header
            == jinja_template.splitlines()[line_no - 1]
        )

    def test_format_error_message_with_content_line(self):
        expected_error_msg = (
            "Unable to parse Jinja template due to syntax error: "
            "unexpected '}' on line 4: {% if 1 == 1 % }"
        )
        error_msg = JinjaSyntaxParsingException.format_error_message(
            syntax_error="unexpected '}'",
            line_number=4,
            line_content="{% if 1 == 1 % }",
        )
        assert error_msg == expected_error_msg

    @pytest.mark.parametrize(
        "line_content",
        (
            "",
            None,
        ),
    )
    def test_format_error_message_without_content_line(self, line_content):
        expected_error_msg = (
            "Unable to parse Jinja template due to syntax error: "
            "unexpected '}' on line 4"
        )
        error_msg = JinjaSyntaxParsingException.format_error_message(
            syntax_error="unexpected '}'",
            line_number=4,
            line_content=line_content,
        )
        assert error_msg == expected_error_msg
