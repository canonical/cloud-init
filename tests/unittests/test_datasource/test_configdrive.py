from copy import copy
import json
import os
import os.path

from cloudinit.sources import DataSourceConfigDrive
from mocker import MockerTestCase


PUBKEY = u'ssh-rsa AAAAB3NzaC1....sIkJhq8wdX+4I3A4cYbYP ubuntu@server-460\n'
EC2_META = {
    'ami-id': 'ami-00000001',
    'ami-launch-index': 0,
    'ami-manifest-path': 'FIXME',
    'block-device-mapping': {
        'ami': 'sda1',
        'ephemeral0': 'sda2',
        'root': '/dev/sda1',
        'swap': 'sda3'},
    'hostname': 'sm-foo-test.novalocal',
    'instance-action': 'none',
    'instance-id': 'i-00000001',
    'instance-type': 'm1.tiny',
    'local-hostname': 'sm-foo-test.novalocal',
    'local-ipv4': None,
    'placement': {'availability-zone': 'nova'},
    'public-hostname': 'sm-foo-test.novalocal',
    'public-ipv4': '',
    'public-keys': {'0': {'openssh-key': PUBKEY}},
    'reservation-id': 'r-iru5qm4m',
    'security-groups': ['default']
}
USER_DATA = '#!/bin/sh\necho This is user data\n'
OSTACK_META = {
    'availability_zone': 'nova',
    'files': [{'content_path': '/content/0000', 'path': '/etc/foo.cfg'},
              {'content_path': '/content/0001', 'path': '/etc/bar/bar.cfg'}],
    'hostname': 'sm-foo-test.novalocal',
    'meta': {'dsmode': 'local', 'my-meta': 'my-value'},
    'name': 'sm-foo-test',
    'public_keys': {'mykey': PUBKEY},
    'uuid': 'b0fa911b-69d4-4476-bbe2-1c92bff6535c'}

CONTENT_0 = 'This is contents of /etc/foo.cfg\n'
CONTENT_1 = '# this is /etc/bar/bar.cfg\n'

CFG_DRIVE_FILES_V2 = {
  'ec2/2009-04-04/meta-data.json': json.dumps(EC2_META),
  'ec2/2009-04-04/user-data': USER_DATA,
  'ec2/latest/meta-data.json': json.dumps(EC2_META),
  'ec2/latest/user-data': USER_DATA,
  'openstack/2012-08-10/meta_data.json': json.dumps(OSTACK_META),
  'openstack/2012-08-10/user_data': USER_DATA,
  'openstack/content/0000': CONTENT_0,
  'openstack/content/0001': CONTENT_1,
  'openstack/latest/meta_data.json': json.dumps(OSTACK_META),
  'openstack/latest/user_data': USER_DATA}


class TestConfigDriveDataSource(MockerTestCase):

    def setUp(self):
        super(TestConfigDriveDataSource, self).setUp()
        # Make a temp directoy for tests to use.
        self.tmp = self.makeDir()

    def test_dir_valid(self):
        """Verify a dir is read as such."""

        my_d = os.path.join(self.tmp, "valid")
        populate_dir(my_d, CFG_DRIVE_FILES_V2)

        found = DataSourceConfigDrive.read_config_drive_dir(my_d)

        self.assertEqual(USER_DATA, found['userdata'])
        self.assertEqual(OSTACK_META, found['metadata'])
        self.assertEqual(found['files']['/etc/foo.cfg'], CONTENT_0)
        self.assertEqual(found['files']['/etc/bar/bar.cfg'], CONTENT_1)

    def test_seed_dir_valid_extra(self):
        """Verify extra files do not affect datasource validity."""

        my_d = os.path.join(self.tmp, "valid_extra")
        data = copy(CFG_DRIVE_FILES_V2)
        data["myfoofile"] = "myfoocontent"

        populate_dir(my_d, data)

#        (userdata, metadata) = DataSourceMAAS.read_maas_seed_dir(my_d)
#
#        self.assertEqual(userdata, data['user-data'])
#        for key in ('instance-id', 'local-hostname'):
#            self.assertEqual(data[key], metadata[key])
#
#        # additional files should not just appear as keys in metadata atm
#        self.assertFalse(('foo' in metadata))
#
#    def test_seed_dir_invalid(self):
#        """Verify that invalid seed_dir raises MAASSeedDirMalformed."""
#
#        valid = {'instance-id': 'i-instanceid',
#            'local-hostname': 'test-hostname', 'user-data': ''}
#
#        my_based = os.path.join(self.tmp, "valid_extra")
#
#        # missing 'userdata' file
#        my_d = "%s-01" % my_based
#        invalid_data = copy(valid)
#        del invalid_data['local-hostname']
#        populate_dir(my_d, invalid_data)
#        self.assertRaises(DataSourceMAAS.MAASSeedDirMalformed,
#                          DataSourceMAAS.read_maas_seed_dir, my_d)
#
#        # missing 'instance-id'
#        my_d = "%s-02" % my_based
#        invalid_data = copy(valid)
#        del invalid_data['instance-id']
#        populate_dir(my_d, invalid_data)
#        self.assertRaises(DataSourceMAAS.MAASSeedDirMalformed,
#                          DataSourceMAAS.read_maas_seed_dir, my_d)
#
#    def test_seed_dir_none(self):
#        """Verify that empty seed_dir raises MAASSeedDirNone."""
#
#        my_d = os.path.join(self.tmp, "valid_empty")
#        self.assertRaises(DataSourceMAAS.MAASSeedDirNone,
#                          DataSourceMAAS.read_maas_seed_dir, my_d)
#
#    def test_seed_dir_missing(self):
#        """Verify that missing seed_dir raises MAASSeedDirNone."""
#        self.assertRaises(DataSourceMAAS.MAASSeedDirNone,
#            DataSourceMAAS.read_maas_seed_dir,
#            os.path.join(self.tmp, "nonexistantdirectory"))
#
#    def test_seed_url_valid(self):
#        """Verify that valid seed_url is read as such."""
#        valid = {'meta-data/instance-id': 'i-instanceid',
#            'meta-data/local-hostname': 'test-hostname',
#            'meta-data/public-keys': 'test-hostname',
#            'user-data': 'foodata'}
#        valid_order = [
#            'meta-data/local-hostname',
#            'meta-data/instance-id',
#            'meta-data/public-keys',
#            'user-data',
#        ]
#        my_seed = "http://example.com/xmeta"
#        my_ver = "1999-99-99"
#        my_headers = {'header1': 'value1', 'header2': 'value2'}
#
#        def my_headers_cb(url):
#            return my_headers
#
#        mock_request = self.mocker.replace(url_helper.readurl,
#            passthrough=False)
#
#        for key in valid_order:
#            url = "%s/%s/%s" % (my_seed, my_ver, key)
#            mock_request(url, headers=my_headers, timeout=None)
#            resp = valid.get(key)
#            self.mocker.result(url_helper.UrlResponse(200, resp))
#        self.mocker.replay()
#
#        (userdata, metadata) = DataSourceMAAS.read_maas_seed_url(my_seed,
#            header_cb=my_headers_cb, version=my_ver)
#
#        self.assertEqual("foodata", userdata)
#        self.assertEqual(metadata['instance-id'],
#            valid['meta-data/instance-id'])
#        self.assertEqual(metadata['local-hostname'],
#            valid['meta-data/local-hostname'])
#
#    def test_seed_url_invalid(self):
#        """Verify that invalid seed_url raises MAASSeedDirMalformed."""
#        pass
#
#    def test_seed_url_missing(self):
#        """Verify seed_url with no found entries raises MAASSeedDirNone."""
#        pass


def populate_dir(seed_dir, files):
    os.mkdir(seed_dir)
    for (name, content) in files.iteritems():
        path = os.path.join(seed_dir, name)
        dirname = os.path.dirname(path)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        with open(path, "w") as fp:
            fp.write(content)
            fp.close()

# vi: ts=4 expandtab
