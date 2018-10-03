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

import mock
import os
import shutil
import tempfile

from cloudinit import helpers
from cloudinit import util

from cloudinit.tests.helpers import CiTestCase

import cloudinit.sources.DataSourceAltCloud as dsac

OS_UNAME_ORIG = getattr(os, 'uname')


def _write_cloud_info_file(value):
    '''
    Populate the CLOUD_INFO_FILE which would be populated
    with a cloud backend identifier ImageFactory when building
    an image with ImageFactory.
    '''
    cifile = open(dsac.CLOUD_INFO_FILE, 'w')
    cifile.write(value)
    cifile.close()
    os.chmod(dsac.CLOUD_INFO_FILE, 0o664)


def _remove_cloud_info_file():
    '''
    Remove the test CLOUD_INFO_FILE
    '''
    os.remove(dsac.CLOUD_INFO_FILE)


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


class TestGetCloudType(CiTestCase):
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
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual('RHEV', dsrc.get_cloud_type())

    def test_vsphere(self):
        '''
        Test method get_cloud_type() for vSphere systems.
        Forcing read_dmi_data return to match a vSphere system: RHEV Hypervisor
        '''
        util.read_dmi_data = _dmi_data('VMware Virtual Platform')
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual('VSPHERE', dsrc.get_cloud_type())

    def test_unknown(self):
        '''
        Test method get_cloud_type() for unknown systems.
        Forcing read_dmi_data return to match an unrecognized return.
        '''
        util.read_dmi_data = _dmi_data('Unrecognized Platform')
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual('UNKNOWN', dsrc.get_cloud_type())


class TestGetDataCloudInfoFile(CiTestCase):
    '''
    Test to exercise method: DataSourceAltCloud.get_data()
    With a contrived CLOUD_INFO_FILE
    '''
    def setUp(self):
        '''Set up.'''
        self.tmp = self.tmp_dir()
        self.paths = helpers.Paths(
            {'cloud_dir': self.tmp, 'run_dir': self.tmp})
        self.cloud_info_file = tempfile.mkstemp()[1]
        self.dmi_data = util.read_dmi_data
        dsac.CLOUD_INFO_FILE = self.cloud_info_file

    def tearDown(self):
        # Reset

        # Attempt to remove the temp file ignoring errors
        try:
            os.remove(self.cloud_info_file)
        except OSError:
            pass

        util.read_dmi_data = self.dmi_data
        dsac.CLOUD_INFO_FILE = '/etc/sysconfig/cloud-info'

    def test_rhev(self):
        '''Success Test module get_data() forcing RHEV.'''

        _write_cloud_info_file('RHEV')
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_rhevm = lambda: True
        self.assertEqual(True, dsrc.get_data())

    def test_vsphere(self):
        '''Success Test module get_data() forcing VSPHERE.'''

        _write_cloud_info_file('VSPHERE')
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_vsphere = lambda: True
        self.assertEqual(True, dsrc.get_data())

    def test_fail_rhev(self):
        '''Failure Test module get_data() forcing RHEV.'''

        _write_cloud_info_file('RHEV')
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_rhevm = lambda: False
        self.assertEqual(False, dsrc.get_data())

    def test_fail_vsphere(self):
        '''Failure Test module get_data() forcing VSPHERE.'''

        _write_cloud_info_file('VSPHERE')
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_vsphere = lambda: False
        self.assertEqual(False, dsrc.get_data())

    def test_unrecognized(self):
        '''Failure Test module get_data() forcing unrecognized.'''

        _write_cloud_info_file('unrecognized')
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.get_data())


class TestGetDataNoCloudInfoFile(CiTestCase):
    '''
    Test to exercise method: DataSourceAltCloud.get_data()
    Without a CLOUD_INFO_FILE
    '''
    def setUp(self):
        '''Set up.'''
        self.tmp = self.tmp_dir()
        self.paths = helpers.Paths(
            {'cloud_dir': self.tmp, 'run_dir': self.tmp})
        self.dmi_data = util.read_dmi_data
        dsac.CLOUD_INFO_FILE = \
            'no such file'
        # We have a different code path for arm to deal with LP1243287
        # We have to switch arch to x86_64 to avoid test failure
        force_arch('x86_64')

    def tearDown(self):
        # Reset
        dsac.CLOUD_INFO_FILE = \
            '/etc/sysconfig/cloud-info'
        util.read_dmi_data = self.dmi_data
        # Return back to original arch
        force_arch()

    def test_rhev_no_cloud_file(self):
        '''Test No cloud info file module get_data() forcing RHEV.'''

        util.read_dmi_data = _dmi_data('RHEV Hypervisor')
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_rhevm = lambda: True
        self.assertEqual(True, dsrc.get_data())

    def test_vsphere_no_cloud_file(self):
        '''Test No cloud info file module get_data() forcing VSPHERE.'''

        util.read_dmi_data = _dmi_data('VMware Virtual Platform')
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        dsrc.user_data_vsphere = lambda: True
        self.assertEqual(True, dsrc.get_data())

    def test_failure_no_cloud_file(self):
        '''Test No cloud info file module get_data() forcing unrecognized.'''

        util.read_dmi_data = _dmi_data('Unrecognized Platform')
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.get_data())


class TestUserDataRhevm(CiTestCase):
    '''
    Test to exercise method: DataSourceAltCloud.user_data_rhevm()
    '''
    def setUp(self):
        '''Set up.'''
        self.paths = helpers.Paths({'cloud_dir': '/tmp'})
        self.mount_dir = self.tmp_dir()
        _write_user_data_files(self.mount_dir, 'test user data')
        self.add_patch(
            'cloudinit.sources.DataSourceAltCloud.modprobe_floppy',
            'm_modprobe_floppy', return_value=None)
        self.add_patch(
            'cloudinit.sources.DataSourceAltCloud.util.udevadm_settle',
            'm_udevadm_settle', return_value=('', ''))
        self.add_patch(
            'cloudinit.sources.DataSourceAltCloud.util.mount_cb',
            'm_mount_cb')

    def test_mount_cb_fails(self):
        '''Test user_data_rhevm() where mount_cb fails.'''

        self.m_mount_cb.side_effect = util.MountFailedError("Failed Mount")
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.user_data_rhevm())

    def test_modprobe_fails(self):
        '''Test user_data_rhevm() where modprobe fails.'''

        self.m_modprobe_floppy.side_effect = util.ProcessExecutionError(
            "Failed modprobe")
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.user_data_rhevm())

    def test_no_modprobe_cmd(self):
        '''Test user_data_rhevm() with no modprobe command.'''

        self.m_modprobe_floppy.side_effect = util.ProcessExecutionError(
            "No such file or dir")
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.user_data_rhevm())

    def test_udevadm_fails(self):
        '''Test user_data_rhevm() where udevadm fails.'''

        self.m_udevadm_settle.side_effect = util.ProcessExecutionError(
            "Failed settle.")
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.user_data_rhevm())

    def test_no_udevadm_cmd(self):
        '''Test user_data_rhevm() with no udevadm command.'''

        self.m_udevadm_settle.side_effect = OSError("No such file or dir")
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.user_data_rhevm())


class TestUserDataVsphere(CiTestCase):
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

        dsac.CLOUD_INFO_FILE = \
            '/etc/sysconfig/cloud-info'

    @mock.patch("cloudinit.sources.DataSourceAltCloud.util.find_devs_with")
    @mock.patch("cloudinit.sources.DataSourceAltCloud.util.mount_cb")
    def test_user_data_vsphere_no_cdrom(self, m_mount_cb, m_find_devs_with):
        '''Test user_data_vsphere() where mount_cb fails.'''

        m_mount_cb.return_value = []
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.user_data_vsphere())
        self.assertEqual(0, m_mount_cb.call_count)

    @mock.patch("cloudinit.sources.DataSourceAltCloud.util.find_devs_with")
    @mock.patch("cloudinit.sources.DataSourceAltCloud.util.mount_cb")
    def test_user_data_vsphere_mcb_fail(self, m_mount_cb, m_find_devs_with):
        '''Test user_data_vsphere() where mount_cb fails.'''

        m_find_devs_with.return_value = ["/dev/mock/cdrom"]
        m_mount_cb.side_effect = util.MountFailedError("Unable To mount")
        dsrc = dsac.DataSourceAltCloud({}, None, self.paths)
        self.assertEqual(False, dsrc.user_data_vsphere())
        self.assertEqual(1, m_find_devs_with.call_count)
        self.assertEqual(1, m_mount_cb.call_count)


class TestReadUserDataCallback(CiTestCase):
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
                         dsac.read_user_data_callback(self.mount_dir))

    def test_callback_dc(self):
        '''Test read_user_data_callback() with only DC file.'''

        _remove_user_data_files(self.mount_dir,
                                dc_file=False,
                                non_dc_file=True)

        self.assertEqual('test user data',
                         dsac.read_user_data_callback(self.mount_dir))

    def test_callback_non_dc(self):
        '''Test read_user_data_callback() with only non-DC file.'''

        _remove_user_data_files(self.mount_dir,
                                dc_file=True,
                                non_dc_file=False)

        self.assertEqual('test user data',
                         dsac.read_user_data_callback(self.mount_dir))

    def test_callback_none(self):
        '''Test read_user_data_callback() no files are found.'''

        _remove_user_data_files(self.mount_dir)
        self.assertIsNone(dsac.read_user_data_callback(self.mount_dir))


def force_arch(arch=None):

    def _os_uname():
        return ('LINUX', 'NODENAME', 'RELEASE', 'VERSION', arch)

    if arch:
        setattr(os, 'uname', _os_uname)
    elif arch is None:
        setattr(os, 'uname', OS_UNAME_ORIG)

# vi: ts=4 expandtab
