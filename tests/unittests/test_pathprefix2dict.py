# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import util

from cloudinit.tests.helpers import TestCase, populate_dir

import shutil
import tempfile


class TestPathPrefix2Dict(TestCase):

    def setUp(self):
        super(TestPathPrefix2Dict, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_required_only(self):
        dirdata = {'f1': b'f1content', 'f2': b'f2content'}
        populate_dir(self.tmp, dirdata)

        ret = util.pathprefix2dict(self.tmp, required=['f1', 'f2'])
        self.assertEqual(dirdata, ret)

    def test_required_missing(self):
        dirdata = {'f1': b'f1content'}
        populate_dir(self.tmp, dirdata)
        kwargs = {'required': ['f1', 'f2']}
        self.assertRaises(ValueError, util.pathprefix2dict, self.tmp, **kwargs)

    def test_no_required_and_optional(self):
        dirdata = {'f1': b'f1c', 'f2': b'f2c'}
        populate_dir(self.tmp, dirdata)

        ret = util.pathprefix2dict(self.tmp, required=None,
                                   optional=['f1', 'f2'])
        self.assertEqual(dirdata, ret)

    def test_required_and_optional(self):
        dirdata = {'f1': b'f1c', 'f2': b'f2c'}
        populate_dir(self.tmp, dirdata)

        ret = util.pathprefix2dict(self.tmp, required=['f1'], optional=['f2'])
        self.assertEqual(dirdata, ret)

# vi: ts=4 expandtab
