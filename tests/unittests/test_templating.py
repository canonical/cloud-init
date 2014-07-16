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

from tests.unittests import helpers as test_helpers

from cloudinit import templater


class TestTemplates(test_helpers.TestCase):
    def test_render_basic(self):
        in_data = """
${b}

c = d
"""
        in_data = in_data.strip()
        expected_data = """
2

c = d
"""
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
