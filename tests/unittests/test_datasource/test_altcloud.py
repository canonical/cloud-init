#! /usr/bin/env python

import os
import stat
import tempfile

from shutil import rmtree
from tempfile import mkdtemp
from unittest import TestCase

from time import sleep

from cloudinit import helpers

# Get the cloudinit.sources.DataSourceAltCloud import items needed.
import cloudinit.sources.DataSourceAltCloud
from cloudinit.sources.DataSourceAltCloud import DataSourceAltCloud

def _write_cloud_info_file(value):
    '''
    Populate the CLOUD_INFO_FILE which would be populated
    with a cloud backend identifier ImageFactory when building
    an image with ImageFactory.
    '''
    f = open(cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE, 'w')
    f.write(value)
    f.close()
    os.chmod(cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE, 0664)

def _remove_cloud_info_file():
    '''
    Remove the test CLOUD_INFO_FILE
    '''
    os.remove(cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE)

def _write_user_data_files(value):
    '''
    Populate the DELTACLOUD_USER_DATA_FILE the USER_DATA_FILE
    which would be populated with user data.
    '''
    f = open(cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE, 'w')
    f.write(value)
    f.close()
    os.chmod(cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE, 0664)

    f = open(cloudinit.sources.DataSourceAltCloud.USER_DATA_FILE, 'w')
    f.write(value)
    f.close()
    os.chmod(cloudinit.sources.DataSourceAltCloud.USER_DATA_FILE, 0664)

def _remove_user_data_files():
    '''
    Remove the test files: DELTACLOUD_USER_DATA_FILE and
    USER_DATA_FILE
    '''
    os.remove(cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE)
    os.remove(cloudinit.sources.DataSourceAltCloud.USER_DATA_FILE)

class TestDataSouceAltCloud_get_cloud_type(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.get_cloud_type() 
    '''

    def setUp(self):
        ''' Set up '''
        self.paths = helpers.Paths({ 'cloud_dir': '/tmp' })

    def tearDown(self):
        # Reset
        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['dmidecode', '--string', 'system-product-name']

    def test_get_cloud_type_RHEV(self):
        '''
        Test method get_cloud_type() for RHEVm systems.
        Forcing dmidecode return to match a RHEVm system: RHEV Hypervisor
        '''
        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['echo', 'RHEV Hypervisor']
        ds = DataSourceAltCloud({}, None, self.paths)
        self.assertEquals('RHEV', \
            ds.get_cloud_type())

    def test_get_cloud_type_VSPHERE(self):
        '''
        Test method get_cloud_type() for vSphere systems.
        Forcing dmidecode return to match a vSphere system: RHEV Hypervisor
        '''
        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['echo', 'VMware Virtual Platform']
        ds = DataSourceAltCloud({}, None, self.paths)
        self.assertEquals('VSPHERE', \
            ds.get_cloud_type())

    def test_get_cloud_type_UNKNOWN(self):
        '''
        Test method get_cloud_type() for unknown systems.
        Forcing dmidecode return to match an unrecognized return.
        '''
        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['echo', 'Unrecognized Platform']
        ds = DataSourceAltCloud({}, None, self.paths)
        self.assertEquals('UNKNOWN', \
            ds.get_cloud_type())

    def test_get_cloud_type_exception1(self):
        '''
        Test method get_cloud_type() where command dmidecode fails.
        '''
        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['ls', 'bad command']
        ds = DataSourceAltCloud({}, None, self.paths)
        self.assertEquals('UNKNOWN', \
            ds.get_cloud_type())

    def test_get_cloud_type_exception(self):
        '''
        Test method get_cloud_type() where command dmidecode is not available.
        '''
        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['bad command']
        ds = DataSourceAltCloud({}, None, self.paths)
        self.assertEquals('UNKNOWN', \
            ds.get_cloud_type())

class TestDataSouceAltCloud_get_data_cloud_info_file(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.get_data() 
    With a contrived CLOUD_INFO_FILE
    '''
    def setUp(self):
        ''' Set up '''
        self.paths = helpers.Paths({ 'cloud_dir': '/tmp' })
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/tmp/cloudinit_test_etc_sysconfig_cloud-info'

    def tearDown(self):
        # Reset
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            CLOUD_INFO_FILE = '/etc/sysconfig/cloud-info'

    def test_get_data_RHEV_cloud_file(self):
        '''Success Test module get_data() forcing RHEV '''

        _write_cloud_info_file('RHEV')
        ds = DataSourceAltCloud({}, None, self.paths)
        ds.user_data_rhevm = lambda : True
        self.assertEquals(True, ds.get_data())

    def test_get_data_VSPHERE_cloud_file(self):
        '''Success Test module get_data() forcing VSPHERE '''

        _write_cloud_info_file('VSPHERE')
        ds = DataSourceAltCloud({}, None, self.paths)
        ds.user_data_vsphere = lambda : True
        self.assertEquals(True, ds.get_data())

    def test_failure_get_data_RHEV_cloud_file(self):
        '''Failure Test module get_data() forcing RHEV '''

        _write_cloud_info_file('RHEV')
        ds = DataSourceAltCloud({}, None, self.paths)
        ds.user_data_rhevm = lambda : False
        self.assertEquals(False, ds.get_data())

    def test_failure_get_data_VSPHERE_cloud_file(self):
        '''Failure Test module get_data() forcing VSPHERE '''

        _write_cloud_info_file('VSPHERE')
        ds = DataSourceAltCloud({}, None, self.paths)
        ds.user_data_vsphere = lambda : False
        self.assertEquals(False, ds.get_data())

    def test_failure_get_data_unrecognized_cloud_file(self):
        '''Failure Test module get_data() forcing unrecognized '''

        _write_cloud_info_file('unrecognized')
        ds = DataSourceAltCloud({}, None, self.paths)
        self.assertEquals(False, ds.get_data())

class TestDataSouceAltCloud_get_data_no_cloud_info_file(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.get_data() 
    Without a CLOUD_INFO_FILE
    '''
    def setUp(self):
        ''' Set up '''
        self.paths = helpers.Paths({ 'cloud_dir': '/tmp' })
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            'no such file'

    def tearDown(self):
        # Reset
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            CLOUD_INFO_FILE = '/etc/sysconfig/cloud-info'
        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['dmidecode', '--string', 'system-product-name']

    def test_get_data_RHEV_cloud_file(self):
        '''Test No cloud info file module get_data() forcing RHEV '''

        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['echo', 'RHEV Hypervisor']
        ds = DataSourceAltCloud({}, None, self.paths)
        ds.user_data_rhevm = lambda : True
        self.assertEquals(True, ds.get_data())

    def test_get_data_VSPHERE_cloud_file(self):
        '''Test No cloud info file module get_data() forcing VSPHERE '''

        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['echo', 'VMware Virtual Platform']
        ds = DataSourceAltCloud({}, None, self.paths)
        ds.user_data_vsphere = lambda : True
        self.assertEquals(True, ds.get_data())

    def test_failure_get_data_VSPHERE_cloud_file(self):
        '''Test No cloud info file module get_data() forcing unrecognized '''

        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['echo', 'Unrecognized Platform']
        ds = DataSourceAltCloud({}, None, self.paths)
        self.assertEquals(False, ds.get_data())

class TestDataSouceAltCloud_user_data_rhevm(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.user_data_rhevm() 
    '''
    def setUp(self):
        ''' Set up '''
        self.paths = helpers.Paths({ 'cloud_dir': '/tmp' })
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/tmp/cloudinit_test_etc_sysconfig_cloud-info'
        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + \
            '/deltacloud-user-data.txt'
        cloudinit.sources.DataSourceAltCloud.USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + \
            '/user-data.txt'

        try:
            os.mkdir(cloudinit.sources.DataSourceAltCloud.MEDIA_DIR)
        except OSError, (errno, strerror):
            # Ignore OSError: [Errno 17] File exists:
            if errno is not 17:
                raise

        _write_user_data_files('test user data')

    def tearDown(self):
        # Reset

        _remove_user_data_files()

        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            CLOUD_INFO_FILE = '/etc/sysconfig/cloud-info'
        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = '/media'

        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['/sbin/modprobe', 'floppy']
        cloudinit.sources.DataSourceAltCloud.CMD_MNT_FLOPPY = \
            ['/bin/mount', '/dev/fd0', cloudinit.sources.DataSourceAltCloud.MEDIA_DIR]

    def test_user_data_rhevm(self):
        '''Test user_data_rhevm() '''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['echo', 'modprobe floppy']
        cloudinit.sources.DataSourceAltCloud.CMD_MNT_FLOPPY = \
            ['echo', 'floppy mounted']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(True, ds.user_data_rhevm())

    def test_user_data_rhevm_modprobe_fails(self):
        '''Test user_data_rhevm() where modprobe fails. '''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['ls', 'modprobe floppy']
        cloudinit.sources.DataSourceAltCloud.CMD_MNT_FLOPPY = \
            ['echo', 'floppy mounted']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(False, ds.user_data_rhevm())

    def test_user_data_rhevm_no_modprobe_cmd(self):
        '''Test user_data_rhevm() with no modprobe command. '''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['bad command', 'modprobe floppy']
        cloudinit.sources.DataSourceAltCloud.CMD_MNT_FLOPPY = \
            ['echo', 'floppy mounted']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(False, ds.user_data_rhevm())

    def test_user_data_rhevm_mount_fails(self):
        '''Test user_data_rhevm() where mount fails. '''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['echo', 'modprobe floppy']
        cloudinit.sources.DataSourceAltCloud.CMD_MNT_FLOPPY = \
            ['ls', 'floppy mounted']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(False, ds.user_data_rhevm())

    def test_user_data_rhevm_no_user_data_file(self):
        '''Test user_data_rhevm() with no user data files.'''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/not-user-data.txt'
        cloudinit.sources.DataSourceAltCloud.USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/not-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['echo', 'modprobe floppy']
        cloudinit.sources.DataSourceAltCloud.CMD_MNT_FLOPPY = \
            ['echo', 'floppy mounted']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(False, ds.user_data_rhevm())

        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'
        cloudinit.sources.DataSourceAltCloud.USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/user-data.txt'

    def test_user_data_rhevm_no_user_data_file(self):
        '''Test user_data_rhevm() with no deltacloud user data file.'''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/not-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['echo', 'modprobe floppy']
        cloudinit.sources.DataSourceAltCloud.CMD_MNT_FLOPPY = \
            ['echo', 'floppy mounted']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(True, ds.user_data_rhevm())

        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'

class TestDataSouceAltCloud_user_data_vsphere(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.user_data_vsphere() 
    '''
    def setUp(self):
        ''' Set up '''
        self.paths = helpers.Paths({ 'cloud_dir': '/tmp' })
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/tmp/cloudinit_test_etc_sysconfig_cloud-info'
        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + \
            '/deltacloud-user-data.txt'
        cloudinit.sources.DataSourceAltCloud.USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + \
            '/user-data.txt'

        try:
            os.mkdir(cloudinit.sources.DataSourceAltCloud.MEDIA_DIR)
        except OSError, (errno, strerror):
            # Ignore OSError: [Errno 17] File exists:
            if errno is not 17:
                raise

        _write_user_data_files('test user data')

    def tearDown(self):
        # Reset

        _remove_user_data_files()

        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            CLOUD_INFO_FILE = '/etc/sysconfig/cloud-info'
        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = '/media'

        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_MNT_CDROM = \
            ['/bin/mount', '/dev/fd0', cloudinit.sources.DataSourceAltCloud.MEDIA_DIR]


    def test_user_data_vsphere(self):
        '''Test user_data_vsphere() '''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_MNT_CDROM = \
            ['echo', 'floppy mounted']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(True, ds.user_data_vsphere())

    def test_user_data_vsphere_mount_fails(self):
        '''Test user_data_vsphere() where mount fails. '''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_MNT_CDROM = \
            ['ls', 'floppy mounted']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(False, ds.user_data_vsphere())

    def test_user_data_vsphere_no_user_data_file(self):
        '''Test user_data_vsphere() with no user data files.'''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/not-user-data.txt'
        cloudinit.sources.DataSourceAltCloud.USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/not-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_MNT_CDROM = \
            ['echo', 'floppy mounted']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(False, ds.user_data_vsphere())

        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'
        cloudinit.sources.DataSourceAltCloud.USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/user-data.txt'

    def test_user_data_vsphere_no_user_data_file(self):
        '''Test user_data_vsphere() with no deltacloud user data files.'''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'
        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/not-user-data.txt'

        cloudinit.sources.DataSourceAltCloud.CMD_MNT_CDROM = \
            ['echo', 'floppy mounted']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(True, ds.user_data_vsphere())

        cloudinit.sources.DataSourceAltCloud.DELTACLOUD_USER_DATA_FILE = \
            cloudinit.sources.DataSourceAltCloud.MEDIA_DIR + '/deltacloud-user-data.txt'

# vi: ts=4 expandtab

