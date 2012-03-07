from unittest import TestCase
from tempfile import mkdtemp
from shutil import rmtree
import os
from copy import copy
from cloudinit.DataSourceMaaS import (
    MaasSeedDirNone,
    MaasSeedDirMalformed,
    read_maas_seed_dir,
)


class TestMaasDataSource(TestCase):

    def setUp(self):
        super(TestMaasDataSource, self).setUp()
        # Make a temp directoy for tests to use.
        self.tmp = mkdtemp(prefix="unittest_")

    def tearDown(self):
        super(TestMaasDataSource, self).tearDown()
        # Clean up temp directory
        rmtree(self.tmp)

    def test_seed_dir_valid(self):
        """Verify a valid seeddir is read as such"""

        data = {'instance-id': 'i-valid01', 'hostname': 'valid01-hostname',
            'user-data': 'valid01-userdata'}

        my_d = os.path.join(self.tmp, "valid")
        populate_dir(my_d, data)

        (userdata, metadata) = read_maas_seed_dir(my_d)

        self.assertEqual(userdata, data['user-data'])
        for key in ('instance-id', 'hostname'):
            self.assertEqual(data[key], metadata[key])

        # verify that 'userdata' is not returned as part of the metadata
        self.assertFalse(('user-data' in metadata))

    def test_seed_dir_valid_extra(self):
        """Verify extra files do not affect seed_dir validity """

        data = {'instance-id': 'i-valid-extra',
            'hostname': 'valid-extra-hostname',
            'user-data': 'valid-extra-userdata', 'foo': 'bar'}

        my_d = os.path.join(self.tmp, "valid_extra")
        populate_dir(my_d, data)

        (userdata, metadata) = read_maas_seed_dir(my_d)

        self.assertEqual(userdata, data['user-data'])
        for key in ('instance-id', 'hostname'):
            self.assertEqual(data[key], metadata[key])

        # additional files should not just appear as keys in metadata atm
        self.assertFalse(('foo' in metadata))

    def test_seed_dir_invalid(self):
        """Verify that invalid seed_dir raises MaasSeedDirMalformed"""

        valid = {'instance-id': 'i-instanceid',
            'hostname': 'test-hostname', 'user-data': ''}

        my_based = os.path.join(self.tmp, "valid_extra")

        # missing 'userdata' file
        my_d = "%s-01" % my_based
        invalid_data = copy(valid)
        del invalid_data['user-data']
        populate_dir(my_d, invalid_data)
        self.assertRaises(MaasSeedDirMalformed, read_maas_seed_dir, my_d)

        # missing 'instance-id'
        my_d = "%s-02" % my_based
        invalid_data = copy(valid)
        del invalid_data['instance-id']
        populate_dir(my_d, invalid_data)
        self.assertRaises(MaasSeedDirMalformed, read_maas_seed_dir, my_d)

    def test_seed_dir_none(self):
        """Verify that empty seed_dir raises MaasSeedDirNone"""

        my_d = os.path.join(self.tmp, "valid_empty")
        self.assertRaises(MaasSeedDirNone, read_maas_seed_dir, my_d)

    def test_seed_dir_missing(self):
        """Verify that missing seed_dir raises MaasSeedDirNone"""
        self.assertRaises(MaasSeedDirNone, read_maas_seed_dir,
            os.path.join(self.tmp, "nonexistantdirectory"))

    def test_seed_url_valid(self):
        """Verify that valid seed_url is read as such"""
        pass

    def test_seed_url_invalid(self):
        """Verify that invalid seed_url raises MaasSeedDirMalformed"""
        pass

    def test_seed_url_missing(self):
        """Verify seed_url with no found entries raises MaasSeedDirNone"""
        pass


def populate_dir(seed_dir, files):
    os.mkdir(seed_dir)
    for (name, content) in files.iteritems():
        with open(os.path.join(seed_dir, name), "w") as fp:
            fp.write(content)
            fp.close()

# vi: ts=4 expandtab
