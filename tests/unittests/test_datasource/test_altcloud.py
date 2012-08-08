#! /usr/bin/env python

import os

from unittest import TestCase
from cloudinit import helpers

# Get the cloudinit.sources.DataSourceAltCloud import items needed.
import cloudinit.sources.DataSourceAltCloud
from cloudinit.sources.DataSourceAltCloud import DataSourceAltCloud
from cloudinit.sources.DataSourceAltCloud import read_user_data_callback

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

def _write_user_data_files(mount_dir, value):
    '''
    Populate the deltacloud_user_data_file the user_data_file
    which would be populated with user data.
    '''
    deltacloud_user_data_file = mount_dir + '/deltacloud-user-data.txt'
    user_data_file = mount_dir + '/user-data.txt'

    f = open(deltacloud_user_data_file, 'w')
    f.write(value)
    f.close()
    os.chmod(deltacloud_user_data_file, 0664)

    f = open(user_data_file, 'w')
    f.write(value)
    f.close()
    os.chmod(user_data_file, 0664)

def _remove_user_data_files(mount_dir,
                            dc_file=True,
                            non_dc_file=True):
    '''
    Remove the test files: deltacloud_user_data_file and
    user_data_file
    '''
    deltacloud_user_data_file = mount_dir + '/deltacloud-user-data.txt'
    user_data_file = mount_dir + '/user-data.txt'

    # Ignore any failures removeing files that are already gone.
    if dc_file:
        try:
            os.remove(deltacloud_user_data_file)
        except OSError:
            pass

    if non_dc_file:
        try:
            os.remove(user_data_file)
        except OSError:
            pass


class TestDataSouceAltCloud_get_cloud_type(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.get_cloud_type() 
    '''

    def setUp(self):
        ''' Set up '''
        self.paths = helpers.Paths({ 'cloud_dir': '/tmp' })
        cloudinit.sources.DataSourceAltCloud.RETRY_TIMES = 1
        cloudinit.sources.DataSourceAltCloud.SLEEP_SECS = 1

    def tearDown(self):
        # Reset
        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['dmidecode', '--string', 'system-product-name']
        cloudinit.sources.DataSourceAltCloud.RETRY_TIMES = 3
        cloudinit.sources.DataSourceAltCloud.SLEEP_SECS = 3

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
        cloudinit.sources.DataSourceAltCloud.RETRY_TIMES = 1
        cloudinit.sources.DataSourceAltCloud.SLEEP_SECS = 1

    def tearDown(self):
        # Reset
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/etc/sysconfig/cloud-info'
        cloudinit.sources.DataSourceAltCloud.RETRY_TIMES = 3
        cloudinit.sources.DataSourceAltCloud.SLEEP_SECS = 3

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
        cloudinit.sources.DataSourceAltCloud.RETRY_TIMES = 1
        cloudinit.sources.DataSourceAltCloud.SLEEP_SECS = 1

    def tearDown(self):
        # Reset
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/etc/sysconfig/cloud-info'
        cloudinit.sources.DataSourceAltCloud.CMD_DMI_SYSTEM = \
            ['dmidecode', '--string', 'system-product-name']
        cloudinit.sources.DataSourceAltCloud.RETRY_TIMES = 3
        cloudinit.sources.DataSourceAltCloud.SLEEP_SECS = 3

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
        self.mount_dir = '/tmp/cloudinit_test_media'

        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/tmp/cloudinit_test_etc_sysconfig_cloud-info'
        cloudinit.sources.DataSourceAltCloud.RETRY_TIMES = 1
        cloudinit.sources.DataSourceAltCloud.SLEEP_SECS = 1

        try:
            os.mkdir(self.mount_dir)
        except OSError, (errno, strerror):
            # Ignore OSError: [Errno 17] File exists:
            if errno is not 17:
                raise

        _write_user_data_files(self.mount_dir, 'test user data')

    def tearDown(self):
        # Reset

        _remove_user_data_files(self.mount_dir)

        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/etc/sysconfig/cloud-info'

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['/sbin/modprobe', 'floppy']
        cloudinit.sources.DataSourceAltCloud.RETRY_TIMES = 3
        cloudinit.sources.DataSourceAltCloud.SLEEP_SECS = 3

    def test_user_data_rhevm(self):
        '''Test user_data_rhevm() where mount_cb fails'''

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['echo', 'modprobe floppy']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(False, ds.user_data_rhevm())

    def test_user_data_rhevm_modprobe_fails(self):
        '''Test user_data_rhevm() where modprobe fails. '''

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['ls', 'modprobe floppy']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(False, ds.user_data_rhevm())

    def test_user_data_rhevm_no_modprobe_cmd(self):
        '''Test user_data_rhevm() with no modprobe command. '''

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['bad command', 'modprobe floppy']

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(False, ds.user_data_rhevm())

class TestDataSouceAltCloud_user_data_vsphere(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.user_data_vsphere() 
    '''
    def setUp(self):
        ''' Set up '''
        self.paths = helpers.Paths({ 'cloud_dir': '/tmp' })
        self.mount_dir = '/tmp/cloudinit_test_media'

        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/tmp/cloudinit_test_etc_sysconfig_cloud-info'
        cloudinit.sources.DataSourceAltCloud.RETRY_TIMES = 1
        cloudinit.sources.DataSourceAltCloud.SLEEP_SECS = 1

        try:
            os.mkdir(self.mount_dir)
        except OSError, (errno, strerror):
            # Ignore OSError: [Errno 17] File exists:
            if errno is not 17:
                raise

        _write_user_data_files(self.mount_dir, 'test user data')

    def tearDown(self):
        # Reset

        _remove_user_data_files(self.mount_dir)

        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/etc/sysconfig/cloud-info'
        cloudinit.sources.DataSourceAltCloud.RETRY_TIMES = 3
        cloudinit.sources.DataSourceAltCloud.SLEEP_SECS = 3

    def test_user_data_vsphere(self):
        '''Test user_data_vsphere() where mount_cb fails'''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = \
            '/tmp/cloudinit_test_media'

        ds = DataSourceAltCloud({}, None, self.paths)

        self.assertEquals(False, ds.user_data_vsphere())

class TestDataSouceAltCloud_read_user_data_callback(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.read_user_data_callback() 
    '''
    def setUp(self):
        ''' Set up '''
        self.paths = helpers.Paths({ 'cloud_dir': '/tmp' })
        self.mount_dir = '/tmp/cloudinit_test_media'

        _write_user_data_files(self.mount_dir, 'test user data')

    def tearDown(self):
        # Reset

        _remove_user_data_files(self.mount_dir)

    def test_read_user_data_callback_both(self):
        '''Test read_user_data_callback() with both files'''

        self.assertEquals('test user data',
            read_user_data_callback(self.mount_dir))

    def test_read_user_data_callback_dc(self):
        '''Test read_user_data_callback() with only DC file'''

        _remove_user_data_files(self.mount_dir,
            dc_file=False,
            non_dc_file=True)

        self.assertEquals('test user data',
            read_user_data_callback(self.mount_dir))

    def test_read_user_data_callback_non_dc(self):
        '''Test read_user_data_callback() with only non-DC file'''

        _remove_user_data_files(self.mount_dir,
            dc_file=True,
            non_dc_file=False)

        self.assertEquals('test user data',
            read_user_data_callback(self.mount_dir))

    def test_read_user_data_callback_none(self):
        '''Test read_user_data_callback() no files are found'''

        _remove_user_data_files(self.mount_dir) 
        self.assertEquals(None, read_user_data_callback(self.mount_dir))

# vi: ts=4 expandtab
