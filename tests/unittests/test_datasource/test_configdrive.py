from copy import copy
import json
import os
import os.path
import shutil
import tempfile
from unittest import TestCase

from cloudinit.sources import DataSourceConfigDrive as ds
from cloudinit import util


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


class TestConfigDriveDataSource(TestCase):

    def setUp(self):
        super(TestConfigDriveDataSource, self).setUp()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        try:
            shutil.rmtree(self.tmp)
        except OSError:
            pass

    def test_dir_valid(self):
        """Verify a dir is read as such."""

        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)

        found = ds.read_config_drive_dir(self.tmp)

        expected_md = copy(OSTACK_META)
        expected_md['instance-id'] = expected_md['uuid']

        self.assertEqual(USER_DATA, found['userdata'])
        self.assertEqual(expected_md, found['metadata'])
        self.assertEqual(found['files']['/etc/foo.cfg'], CONTENT_0)
        self.assertEqual(found['files']['/etc/bar/bar.cfg'], CONTENT_1)

    def test_seed_dir_valid_extra(self):
        """Verify extra files do not affect datasource validity."""

        data = copy(CFG_DRIVE_FILES_V2)
        data["myfoofile.txt"] = "myfoocontent"
        data["openstack/latest/random-file.txt"] = "random-content"

        populate_dir(self.tmp, data)

        found = ds.read_config_drive_dir(self.tmp)

        expected_md = copy(OSTACK_META)
        expected_md['instance-id'] = expected_md['uuid']

        self.assertEqual(expected_md, found['metadata'])

    def test_seed_dir_bad_json_metadata(self):
        """Verify that bad json in metadata raises BrokenConfigDriveDir."""
        data = copy(CFG_DRIVE_FILES_V2)

        data["openstack/2012-08-10/meta_data.json"] = "non-json garbage {}"
        data["openstack/latest/meta_data.json"] = "non-json garbage {}"

        populate_dir(self.tmp, data)

        self.assertRaises(ds.BrokenConfigDriveDir,
                          ds.read_config_drive_dir, self.tmp)

    def test_seed_dir_no_configdrive(self):
        """Verify that no metadata raises NonConfigDriveDir."""

        my_d = os.path.join(self.tmp, "non-configdrive")
        data = copy(CFG_DRIVE_FILES_V2)
        data["myfoofile.txt"] = "myfoocontent"
        data["openstack/latest/random-file.txt"] = "random-content"
        data["content/foo"] = "foocontent"

        self.assertRaises(ds.NonConfigDriveDir,
                          ds.read_config_drive_dir, my_d)

    def test_seed_dir_missing(self):
        """Verify that missing seed_dir raises NonConfigDriveDir."""
        my_d = os.path.join(self.tmp, "nonexistantdirectory")
        self.assertRaises(ds.NonConfigDriveDir,
                          ds.read_config_drive_dir, my_d)

    def test_find_candidates(self):
        devs_with_answers = {
            "TYPE=vfat": [],
            "TYPE=iso9660": ["/dev/vdb"],
            "LABEL=config-2": ["/dev/vdb"],
        }

        def my_devs_with(criteria):
            return devs_with_answers[criteria]

        try:
            orig_find_devs_with = util.find_devs_with
            util.find_devs_with = my_devs_with

            self.assertEqual(["/dev/vdb"], ds.find_candidate_devs())

            # add a vfat item
            # zdd reverse sorts after vdb, but config-2 label is preferred
            devs_with_answers['TYPE=vfat'] = ["/dev/zdd"]
            self.assertEqual(["/dev/vdb", "/dev/zdd"],
                             ds.find_candidate_devs())

            # verify that partitions are not considered
            devs_with_answers = {"TYPE=vfat": ["/dev/sda1"],
                "TYPE=iso9660": [], "LABEL=config-2": ["/dev/vdb3"]}
            self.assertEqual([], ds.find_candidate_devs())

        finally:
            util.find_devs_with = orig_find_devs_with


def populate_dir(seed_dir, files):
    for (name, content) in files.iteritems():
        path = os.path.join(seed_dir, name)
        dirname = os.path.dirname(path)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        with open(path, "w") as fp:
            fp.write(content)
            fp.close()

# vi: ts=4 expandtab
