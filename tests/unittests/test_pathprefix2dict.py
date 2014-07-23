from cloudinit import util

from mocker import MockerTestCase
from .helpers import populate_dir


class TestPathPrefix2Dict(MockerTestCase):

    def setUp(self):
        self.tmp = self.makeDir()

    def test_required_only(self):
        dirdata = {'f1': 'f1content', 'f2': 'f2content'}
        populate_dir(self.tmp, dirdata)

        ret = util.pathprefix2dict(self.tmp, required=['f1', 'f2'])
        self.assertEqual(dirdata, ret)

    def test_required_missing(self):
        dirdata = {'f1': 'f1content'}
        populate_dir(self.tmp, dirdata)
        kwargs = {'required': ['f1', 'f2']}
        self.assertRaises(ValueError, util.pathprefix2dict, self.tmp, **kwargs)

    def test_no_required_and_optional(self):
        dirdata = {'f1': 'f1c', 'f2': 'f2c'}
        populate_dir(self.tmp, dirdata)

        ret = util.pathprefix2dict(self.tmp, required=None,
                                  optional=['f1', 'f2'])
        self.assertEqual(dirdata, ret)

    def test_required_and_optional(self):
        dirdata = {'f1': 'f1c', 'f2': 'f2c'}
        populate_dir(self.tmp, dirdata)

        ret = util.pathprefix2dict(self.tmp, required=['f1'], optional=['f2'])
        self.assertEqual(dirdata, ret)

# vi: ts=4 expandtab
