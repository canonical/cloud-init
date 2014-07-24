from copy import copy
import json
import os
import os.path

import mocker
from mocker import MockerTestCase

from cloudinit import helpers
from cloudinit import settings
from cloudinit.sources import DataSourceConfigDrive as ds
from cloudinit.sources.helpers import openstack
from cloudinit import util

from .. import helpers as unit_helpers

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
        self.tmp = self.makeDir()

    def test_ec2_metadata(self):
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        found = ds.read_config_drive(self.tmp)
        self.assertTrue('ec2-metadata' in found)
        ec2_md = found['ec2-metadata']
        self.assertEqual(EC2_META, ec2_md)

    def test_dev_os_remap(self):
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        cfg_ds = ds.DataSourceConfigDrive(settings.CFG_BUILTIN,
                                          None,
                                          helpers.Paths({}))
        found = ds.read_config_drive(self.tmp)
        cfg_ds.metadata = found['metadata']
        name_tests = {
            'ami': '/dev/vda1',
            'root': '/dev/vda1',
            'ephemeral0': '/dev/vda2',
            'swap': '/dev/vda3',
        }
        for name, dev_name in name_tests.items():
            with unit_helpers.mocker() as my_mock:
                find_mock = my_mock.replace(util.find_devs_with,
                                            spec=False, passthrough=False)
                provided_name = dev_name[len('/dev/'):]
                provided_name = "s" + provided_name[1:]
                find_mock(mocker.ARGS)
                my_mock.result([provided_name])
                exists_mock = my_mock.replace(os.path.exists,
                                              spec=False, passthrough=False)
                exists_mock(mocker.ARGS)
                my_mock.result(False)
                exists_mock(mocker.ARGS)
                my_mock.result(True)
                my_mock.replay()
                device = cfg_ds.device_name_to_device(name)
                self.assertEquals(dev_name, device)

    def test_dev_os_map(self):
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        cfg_ds = ds.DataSourceConfigDrive(settings.CFG_BUILTIN,
                                          None,
                                          helpers.Paths({}))
        found = ds.read_config_drive(self.tmp)
        os_md = found['metadata']
        cfg_ds.metadata = os_md
        name_tests = {
            'ami': '/dev/vda1',
            'root': '/dev/vda1',
            'ephemeral0': '/dev/vda2',
            'swap': '/dev/vda3',
        }
        for name, dev_name in name_tests.items():
            with unit_helpers.mocker() as my_mock:
                find_mock = my_mock.replace(util.find_devs_with,
                                            spec=False, passthrough=False)
                find_mock(mocker.ARGS)
                my_mock.result([dev_name])
                exists_mock = my_mock.replace(os.path.exists,
                                              spec=False, passthrough=False)
                exists_mock(mocker.ARGS)
                my_mock.result(True)
                my_mock.replay()
                device = cfg_ds.device_name_to_device(name)
                self.assertEquals(dev_name, device)

    def test_dev_ec2_remap(self):
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        cfg_ds = ds.DataSourceConfigDrive(settings.CFG_BUILTIN,
                                          None,
                                          helpers.Paths({}))
        found = ds.read_config_drive(self.tmp)
        ec2_md = found['ec2-metadata']
        os_md = found['metadata']
        cfg_ds.ec2_metadata = ec2_md
        cfg_ds.metadata = os_md
        name_tests = {
            'ami': '/dev/vda1',
            'root': '/dev/vda1',
            'ephemeral0': '/dev/vda2',
            'swap': '/dev/vda3',
            None: None,
            'bob': None,
            'root2k': None,
        }
        for name, dev_name in name_tests.items():
            with unit_helpers.mocker(verify_calls=False) as my_mock:
                exists_mock = my_mock.replace(os.path.exists,
                                              spec=False, passthrough=False)
                exists_mock(mocker.ARGS)
                my_mock.result(False)
                exists_mock(mocker.ARGS)
                my_mock.result(True)
                my_mock.replay()
                device = cfg_ds.device_name_to_device(name)
                self.assertEquals(dev_name, device)

    def test_dev_ec2_map(self):
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        cfg_ds = ds.DataSourceConfigDrive(settings.CFG_BUILTIN,
                                          None,
                                          helpers.Paths({}))
        found = ds.read_config_drive(self.tmp)
        exists_mock = self.mocker.replace(os.path.exists,
                                          spec=False, passthrough=False)
        exists_mock(mocker.ARGS)
        self.mocker.count(0, None)
        self.mocker.result(True)
        self.mocker.replay()
        ec2_md = found['ec2-metadata']
        os_md = found['metadata']
        cfg_ds.ec2_metadata = ec2_md
        cfg_ds.metadata = os_md
        name_tests = {
            'ami': '/dev/sda1',
            'root': '/dev/sda1',
            'ephemeral0': '/dev/sda2',
            'swap': '/dev/sda3',
            None: None,
            'bob': None,
            'root2k': None,
        }
        for name, dev_name in name_tests.items():
            device = cfg_ds.device_name_to_device(name)
            self.assertEquals(dev_name, device)

    def test_dir_valid(self):
        """Verify a dir is read as such."""

        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)

        found = ds.read_config_drive(self.tmp)

        expected_md = copy(OSTACK_META)
        expected_md['instance-id'] = expected_md['uuid']
        expected_md['local-hostname'] = expected_md['hostname']

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

        found = ds.read_config_drive(self.tmp)

        expected_md = copy(OSTACK_META)
        expected_md['instance-id'] = expected_md['uuid']
        expected_md['local-hostname'] = expected_md['hostname']

        self.assertEqual(expected_md, found['metadata'])

    def test_seed_dir_bad_json_metadata(self):
        """Verify that bad json in metadata raises BrokenConfigDriveDir."""
        data = copy(CFG_DRIVE_FILES_V2)

        data["openstack/2012-08-10/meta_data.json"] = "non-json garbage {}"
        data["openstack/latest/meta_data.json"] = "non-json garbage {}"

        populate_dir(self.tmp, data)

        self.assertRaises(openstack.BrokenMetadata,
                          ds.read_config_drive, self.tmp)

    def test_seed_dir_no_configdrive(self):
        """Verify that no metadata raises NonConfigDriveDir."""

        my_d = os.path.join(self.tmp, "non-configdrive")
        data = copy(CFG_DRIVE_FILES_V2)
        data["myfoofile.txt"] = "myfoocontent"
        data["openstack/latest/random-file.txt"] = "random-content"
        data["content/foo"] = "foocontent"

        self.assertRaises(openstack.NonReadable,
                          ds.read_config_drive, my_d)

    def test_seed_dir_missing(self):
        """Verify that missing seed_dir raises NonConfigDriveDir."""
        my_d = os.path.join(self.tmp, "nonexistantdirectory")
        self.assertRaises(openstack.NonReadable,
                          ds.read_config_drive, my_d)

    def test_find_candidates(self):
        devs_with_answers = {}

        def my_devs_with(*args, **kwargs):
            criteria = args[0] if len(args) else kwargs.pop('criteria', None)
            return devs_with_answers.get(criteria, [])

        def my_is_partition(dev):
            return dev[-1] in "0123456789" and not dev.startswith("sr")

        try:
            orig_find_devs_with = util.find_devs_with
            util.find_devs_with = my_devs_with

            orig_is_partition = util.is_partition
            util.is_partition = my_is_partition

            devs_with_answers = {"TYPE=vfat": [],
                "TYPE=iso9660": ["/dev/vdb"],
                "LABEL=config-2": ["/dev/vdb"],
            }
            self.assertEqual(["/dev/vdb"], ds.find_candidate_devs())

            # add a vfat item
            # zdd reverse sorts after vdb, but config-2 label is preferred
            devs_with_answers['TYPE=vfat'] = ["/dev/zdd"]
            self.assertEqual(["/dev/vdb", "/dev/zdd"],
                             ds.find_candidate_devs())

            # verify that partitions are considered, that have correct label.
            devs_with_answers = {"TYPE=vfat": ["/dev/sda1"],
                "TYPE=iso9660": [], "LABEL=config-2": ["/dev/vdb3"]}
            self.assertEqual(["/dev/vdb3"],
                              ds.find_candidate_devs())

        finally:
            util.find_devs_with = orig_find_devs_with
            util.is_partition = orig_is_partition

    def test_pubkeys_v2(self):
        """Verify that public-keys work in config-drive-v2."""
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        myds = cfg_ds_from_dir(self.tmp)
        self.assertEqual(myds.get_public_ssh_keys(),
           [OSTACK_META['public_keys']['mykey']])


def cfg_ds_from_dir(seed_d):
    found = ds.read_config_drive(seed_d)
    cfg_ds = ds.DataSourceConfigDrive(settings.CFG_BUILTIN, None,
                                      helpers.Paths({}))
    populate_ds_from_read_config(cfg_ds, seed_d, found)
    return cfg_ds


def populate_ds_from_read_config(cfg_ds, source, results):
    """Patch the DataSourceConfigDrive from the results of
    read_config_drive_dir hopefully in line with what it would have
    if cfg_ds.get_data had been successfully called"""
    cfg_ds.source = source
    cfg_ds.metadata = results.get('metadata')
    cfg_ds.ec2_metadata = results.get('ec2-metadata')
    cfg_ds.userdata_raw = results.get('userdata')
    cfg_ds.version = results.get('version')


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
