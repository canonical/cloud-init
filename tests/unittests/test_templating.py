# vi: ts=4 expandtab
#
#    Copyright (C) 2014 Yahoo! Inc.
#
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from . import helpers as test_helpers
import textwrap

from cloudinit import templater


class TestTemplates(test_helpers.TestCase):
    def test_render_basic(self):
        in_data = textwrap.dedent("""
            ${b}

            c = d
            """)
        in_data = in_data.strip()
        expected_data = textwrap.dedent("""
            2

            c = d
            """)
        out_data = templater.basic_render(in_data, {'b': 2})
        self.assertEqual(expected_data.strip(), out_data)

    def test_detection(self):
        blob = "## template:cheetah"

        (template_type, renderer, contents) = templater.detect_template(blob)
        self.assertIn("cheetah", template_type)
        self.assertEqual("", contents.strip())

        blob = "blahblah $blah"
        (template_type, renderer, contents) = templater.detect_template(blob)
        self.assertIn("cheetah", template_type)
        self.assertEquals(blob, contents)

        blob = '##template:something-new'
        self.assertRaises(ValueError, templater.detect_template, blob)

    def test_render_cheetah(self):
        blob = '''## template:cheetah
$a,$b'''
        c = templater.render_string(blob, {"a": 1, "b": 2})
        self.assertEquals("1,2", c)

    def test_render_jinja(self):
        blob = '''## template:jinja
{{a}},{{b}}'''
        c = templater.render_string(blob, {"a": 1, "b": 2})
        self.assertEquals("1,2", c)

    def test_render_default(self):
        blob = '''$a,$b'''
        c = templater.render_string(blob, {"a": 1, "b": 2})
        self.assertEquals("1,2", c)

    def test_render_basic_deeper(self):
        hn = 'myfoohost.yahoo.com'
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
        out_data = templater.basic_render(in_data, {'hostname': hn})
        self.assertEqual(expected_data, out_data)

    def test_render_basic_parens(self):
        hn = "myfoohost"
        in_data = "h = ${hostname}\nc=d\n"
        expected_data = "h = %s\nc=d\n" % hn
        out_data = templater.basic_render(in_data, {'hostname': hn})
        self.assertEqual(expected_data, out_data)

    def test_render_basic2(self):
        mirror = "mymirror"
        codename = "zany"
        in_data = "deb $mirror $codename-updates main contrib non-free"
        ex_data = "deb %s %s-updates main contrib non-free" % (mirror, codename)

        out_data = templater.basic_render(in_data,
            {'mirror': mirror, 'codename': codename})
        self.assertEqual(ex_data, out_data)
