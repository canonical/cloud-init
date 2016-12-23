# Copyright (C) 2014 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from __future__ import print_function

from . import helpers as test_helpers
import textwrap

from cloudinit import templater

try:
    import Cheetah
    HAS_CHEETAH = True
    Cheetah  # make pyflakes happy, as Cheetah is not used here
except ImportError:
    HAS_CHEETAH = False


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

    @test_helpers.skipIf(not HAS_CHEETAH, 'cheetah renderer not available')
    def test_detection(self):
        blob = "## template:cheetah"

        (template_type, renderer, contents) = templater.detect_template(blob)
        self.assertIn("cheetah", template_type)
        self.assertEqual("", contents.strip())

        blob = "blahblah $blah"
        (template_type, renderer, contents) = templater.detect_template(blob)
        self.assertIn("cheetah", template_type)
        self.assertEqual(blob, contents)

        blob = '##template:something-new'
        self.assertRaises(ValueError, templater.detect_template, blob)

    def test_render_cheetah(self):
        blob = '''## template:cheetah
$a,$b'''
        c = templater.render_string(blob, {"a": 1, "b": 2})
        self.assertEqual("1,2", c)

    def test_render_jinja(self):
        blob = '''## template:jinja
{{a}},{{b}}'''
        c = templater.render_string(blob, {"a": 1, "b": 2})
        self.assertEqual("1,2", c)

    def test_render_default(self):
        blob = '''$a,$b'''
        c = templater.render_string(blob, {"a": 1, "b": 2})
        self.assertEqual("1,2", c)

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
        ex_data = "deb %s %s-updates main contrib non-free" % (mirror,
                                                               codename)

        out_data = templater.basic_render(in_data,
                                          {'mirror': mirror,
                                           'codename': codename})
        self.assertEqual(ex_data, out_data)

# vi: ts=4 expandtab
