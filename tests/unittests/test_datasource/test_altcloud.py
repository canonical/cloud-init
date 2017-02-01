# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joe VLcek <JVLcek@RedHat.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

'''
This test file exercises the code in sources DataSourceAltCloud.py
'''

import os
import shutil
import tempfile

from cloudinit import helpers
from cloudinit import util
from unittest import TestCase

# Get the cloudinit.sources.DataSourceAltCloud import items needed.
import cloudinit.sources.DataSourceAltCloud
from cloudinit.sources.DataSourceAltCloud import DataSourceAltCloud
from cloudinit.sources.DataSourceAltCloud import read_user_data_callback

OS_UNAME_ORIG = getattr(os, 'uname')


def _write_cloud_info_file(value):
    '''
    Populate the CLOUD_INFO_FILE which would be populated
    with a cloud backend identifier ImageFactory when building
    an image with ImageFactory.
    '''
    cifile = open(cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE, 'w')
    cifile.write(value)
    cifile.close()
    os.chmod(cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE, 0o664)


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

    udfile = open(deltacloud_user_data_file, 'w')
    udfile.write(value)
    udfile.close()
    os.chmod(deltacloud_user_data_file, 0o664)

    udfile = open(user_data_file, 'w')
    udfile.write(value)
    udfile.close()
    os.chmod(user_data_file, 0o664)


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


def _dmi_data(expected):
    '''
    Spoof the data received over DMI
    '''
    def _data(key):
        return expected

    return _data


class TestGetCloudType(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.get_cloud_type()
    '''

    def setUp(self):
        '''Set up.'''
        self.paths = helpers.Paths({'cloud_dir': '/tmp'})
        self.dmi_data = util.read_dmi_data
        # We have a different code path for arm to deal with LP1243287
        # We have to switch arch to x86_64 to avoid test failure
        force_arch('x86_64')

    def tearDown(self):
        # Reset
        util.read_dmi_data = self.dmi_data
        force_arch()

    def test_rhev(self):
        '''
        Test method get_cloud_type() for RHEVm systems.
        Forcing read_dmi_data return to match a RHEVm system: RHEV Hypervisor
        '''
        util.read_dmi_data = _dmi_data('RHEV')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        self.assertEqual('RHEV', dsrc.get_cloud_type())

    def test_vsphere(self):
        '''
        Test method get_cloud_type() for vSphere systems.
        Forcing read_dmi_data return to match a vSphere system: RHEV Hypervisor
        '''
        util.read_dmi_data = _dmi_data('VMware Virtual Platform')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        self.assertEqual('VSPHERE', dsrc.get_cloud_type())

    def test_unknown(self):
        '''
        Test method get_cloud_type() for unknown systems.
        Forcing read_dmi_data return to match an unrecognized return.
        '''
        util.read_dmi_data = _dmi_data('Unrecognized Platform')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        self.assertEqual('UNKNOWN', dsrc.get_cloud_type())


class TestGetDataCloudInfoFile(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.get_data()
    With a contrived CLOUD_INFO_FILE
    '''
    def setUp(self):
        '''Set up.'''
        self.paths = helpers.Paths({'cloud_dir': '/tmp'})
        self.cloud_info_file = tempfile.mkstemp()[1]
        self.dmi_data = util.read_dmi_data
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            self.cloud_info_file

    def tearDown(self):
        # Reset

        # Attempt to remove the temp file ignoring errors
        try:
            os.remove(self.cloud_info_file)
        except OSError:
            pass

        util.read_dmi_data = self.dmi_data
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/etc/sysconfig/cloud-info'

    def test_rhev(self):
        '''Success Test module get_data() forcing RHEV.'''

        _write_cloud_info_file('RHEV')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_rhevm = lambda: True
        self.assertEqual(True, dsrc.get_data())

    def test_vsphere(self):
        '''Success Test module get_data() forcing VSPHERE.'''

        _write_cloud_info_file('VSPHERE')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_vsphere = lambda: True
        self.assertEqual(True, dsrc.get_data())

    def test_fail_rhev(self):
        '''Failure Test module get_data() forcing RHEV.'''

        _write_cloud_info_file('RHEV')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_rhevm = lambda: False
        self.assertEqual(False, dsrc.get_data())

    def test_fail_vsphere(self):
        '''Failure Test module get_data() forcing VSPHERE.'''

        _write_cloud_info_file('VSPHERE')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_vsphere = lambda: False
        self.assertEqual(False, dsrc.get_data())

    def test_unrecognized(self):
        '''Failure Test module get_data() forcing unrecognized.'''

        _write_cloud_info_file('unrecognized')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.get_data())


class TestGetDataNoCloudInfoFile(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.get_data()
    Without a CLOUD_INFO_FILE
    '''
    def setUp(self):
        '''Set up.'''
        self.paths = helpers.Paths({'cloud_dir': '/tmp'})
        self.dmi_data = util.read_dmi_data
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            'no such file'
        # We have a different code path for arm to deal with LP1243287
        # We have to switch arch to x86_64 to avoid test failure
        force_arch('x86_64')

    def tearDown(self):
        # Reset
        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/etc/sysconfig/cloud-info'
        util.read_dmi_data = self.dmi_data
        # Return back to original arch
        force_arch()

    def test_rhev_no_cloud_file(self):
        '''Test No cloud info file module get_data() forcing RHEV.'''

        util.read_dmi_data = _dmi_data('RHEV Hypervisor')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_rhevm = lambda: True
        self.assertEqual(True, dsrc.get_data())

    def test_vsphere_no_cloud_file(self):
        '''Test No cloud info file module get_data() forcing VSPHERE.'''

        util.read_dmi_data = _dmi_data('VMware Virtual Platform')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_vsphere = lambda: True
        self.assertEqual(True, dsrc.get_data())

    def test_failure_no_cloud_file(self):
        '''Test No cloud info file module get_data() forcing unrecognized.'''

        util.read_dmi_data = _dmi_data('Unrecognized Platform')
        dsrc = DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.get_data())


class TestUserDataRhevm(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.user_data_rhevm()
    '''
    def setUp(self):
        '''Set up.'''
        self.paths = helpers.Paths({'cloud_dir': '/tmp'})
        self.mount_dir = tempfile.mkdtemp()

        _write_user_data_files(self.mount_dir, 'test user data')

    def tearDown(self):
        # Reset

        _remove_user_data_files(self.mount_dir)

        # Attempt to remove the temp dir ignoring errors
        try:
            shutil.rmtree(self.mount_dir)
        except OSError:
            pass

        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/etc/sysconfig/cloud-info'
        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['/sbin/modprobe', 'floppy']
        cloudinit.sources.DataSourceAltCloud.CMD_UDEVADM_SETTLE = \
            ['/sbin/udevadm', 'settle', '--quiet', '--timeout=5']

    def test_mount_cb_fails(self):
        '''Test user_data_rhevm() where mount_cb fails.'''

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['echo', 'modprobe floppy']

        dsrc = DataSourceAltCloud({}, None, self.paths)

        self.assertEqual(False, dsrc.user_data_rhevm())

    def test_modprobe_fails(self):
        '''Test user_data_rhevm() where modprobe fails.'''

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['ls', 'modprobe floppy']

        dsrc = DataSourceAltCloud({}, None, self.paths)

        self.assertEqual(False, dsrc.user_data_rhevm())

    def test_no_modprobe_cmd(self):
        '''Test user_data_rhevm() with no modprobe command.'''

        cloudinit.sources.DataSourceAltCloud.CMD_PROBE_FLOPPY = \
            ['bad command', 'modprobe floppy']

        dsrc = DataSourceAltCloud({}, None, self.paths)

        self.assertEqual(False, dsrc.user_data_rhevm())

    def test_udevadm_fails(self):
        '''Test user_data_rhevm() where udevadm fails.'''

        cloudinit.sources.DataSourceAltCloud.CMD_UDEVADM_SETTLE = \
            ['ls', 'udevadm floppy']

        dsrc = DataSourceAltCloud({}, None, self.paths)

        self.assertEqual(False, dsrc.user_data_rhevm())

    def test_no_udevadm_cmd(self):
        '''Test user_data_rhevm() with no udevadm command.'''

        cloudinit.sources.DataSourceAltCloud.CMD_UDEVADM_SETTLE = \
            ['bad command', 'udevadm floppy']

        dsrc = DataSourceAltCloud({}, None, self.paths)

        self.assertEqual(False, dsrc.user_data_rhevm())


class TestUserDataVsphere(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.user_data_vsphere()
    '''
    def setUp(self):
        '''Set up.'''
        self.paths = helpers.Paths({'cloud_dir': '/tmp'})
        self.mount_dir = tempfile.mkdtemp()

        _write_user_data_files(self.mount_dir, 'test user data')

    def tearDown(self):
        # Reset

        _remove_user_data_files(self.mount_dir)

        # Attempt to remove the temp dir ignoring errors
        try:
            shutil.rmtree(self.mount_dir)
        except OSError:
            pass

        cloudinit.sources.DataSourceAltCloud.CLOUD_INFO_FILE = \
            '/etc/sysconfig/cloud-info'

    def test_user_data_vsphere(self):
        '''Test user_data_vsphere() where mount_cb fails.'''

        cloudinit.sources.DataSourceAltCloud.MEDIA_DIR = self.mount_dir

        dsrc = DataSourceAltCloud({}, None, self.paths)

        self.assertEqual(False, dsrc.user_data_vsphere())


class TestReadUserDataCallback(TestCase):
    '''
    Test to exercise method: DataSourceAltCloud.read_user_data_callback()
    '''
    def setUp(self):
        '''Set up.'''
        self.paths = helpers.Paths({'cloud_dir': '/tmp'})
        self.mount_dir = tempfile.mkdtemp()

        _write_user_data_files(self.mount_dir, 'test user data')

    def tearDown(self):
        # Reset

        _remove_user_data_files(self.mount_dir)

        # Attempt to remove the temp dir ignoring errors
        try:
            shutil.rmtree(self.mount_dir)
        except OSError:
            pass

    def test_callback_both(self):
        '''Test read_user_data_callback() with both files.'''

        self.assertEqual('test user data',
                         read_user_data_callback(self.mount_dir))

    def test_callback_dc(self):
        '''Test read_user_data_callback() with only DC file.'''

        _remove_user_data_files(self.mount_dir,
                                dc_file=False,
                                non_dc_file=True)

        self.assertEqual('test user data',
                         read_user_data_callback(self.mount_dir))

    def test_callback_non_dc(self):
        '''Test read_user_data_callback() with only non-DC file.'''

        _remove_user_data_files(self.mount_dir,
                                dc_file=True,
                                non_dc_file=False)

        self.assertEqual('test user data',
                         read_user_data_callback(self.mount_dir))

    def test_callback_none(self):
        '''Test read_user_data_callback() no files are found.'''

        _remove_user_data_files(self.mount_dir)
        self.assertEqual(None, read_user_data_callback(self.mount_dir))


def force_arch(arch=None):

    def _os_uname():
        return ('LINUX', 'NODENAME', 'RELEASE', 'VERSION', arch)

    if arch:
        setattr(os, 'uname', _os_uname)
    elif arch is None:
        setattr(os, 'uname', OS_UNAME_ORIG)

# vi: ts=4 expandtab
