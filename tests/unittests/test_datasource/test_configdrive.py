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
        data["myfoofile.txt"] = "myfoocontent"
        data["openstack/latest/random-file.txt"] = "random-content"

        populate_dir(my_d, data)

        found = DataSourceConfigDrive.read_config_drive_dir(my_d)
        self.assertEqual(OSTACK_META, found['metadata'])

    def test_seed_dir_bad_json_metadata(self):
        """Verify that bad json in metadata raises BrokenConfigDriveDir."""
        my_d = os.path.join(self.tmp, "bad-json-metadata")
        data = copy(CFG_DRIVE_FILES_V2)

        data["openstack/2012-08-10/meta_data.json"] = "non-json garbage {}"
        data["openstack/latest/meta_data.json"] = "non-json garbage {}"

        populate_dir(my_d, data)

        self.assertRaises(DataSourceConfigDrive.BrokenConfigDriveDir,
                          DataSourceConfigDrive.read_config_drive_dir, my_d)

    def test_seed_dir_no_configdrive(self):
        """Verify that no metadata raises NonConfigDriveDir."""

        my_d = os.path.join(self.tmp, "non-configdrive")
        data = copy(CFG_DRIVE_FILES_V2)
        data["myfoofile.txt"] = "myfoocontent"
        data["openstack/latest/random-file.txt"] = "random-content"
        data["content/foo"] = "foocontent"

        self.assertRaises(DataSourceConfigDrive.NonConfigDriveDir,
                          DataSourceConfigDrive.read_config_drive_dir, my_d)

    def test_seed_dir_missing(self):
        """Verify that missing seed_dir raises NonConfigDriveDir."""
        my_d = os.path.join(self.tmp, "nonexistantdirectory")
        self.assertRaises(DataSourceConfigDrive.NonConfigDriveDir,
                          DataSourceConfigDrive.read_config_drive_dir, my_d)


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
