# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joe VLcek <JVLcek@RedHat.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
This test file exercises the code in sources DataSourceAltCloud.py
"""

import os
import shutil

import pytest

import cloudinit.sources.DataSourceAltCloud as dsac
from cloudinit import dmi, subp, util
from tests.unittests.helpers import mock

OS_UNAME_ORIG = getattr(os, "uname")


def _write_user_data_files(mount_dir, value):
    """
    Populate the deltacloud_user_data_file the user_data_file
    which would be populated with user data.
    """
    deltacloud_user_data_file = mount_dir + "/deltacloud-user-data.txt"
    user_data_file = mount_dir + "/user-data.txt"

    udfile = open(deltacloud_user_data_file, "w")
    udfile.write(value)
    udfile.close()
    os.chmod(deltacloud_user_data_file, 0o664)

    udfile = open(user_data_file, "w")
    udfile.write(value)
    udfile.close()
    os.chmod(user_data_file, 0o664)


def _remove_user_data_files(mount_dir, dc_file=True, non_dc_file=True):
    """
    Remove the test files: deltacloud_user_data_file and
    user_data_file
    """
    deltacloud_user_data_file = mount_dir + "/deltacloud-user-data.txt"
    user_data_file = mount_dir + "/user-data.txt"

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
    """
    Spoof the data received over DMI
    """

    def _data(key):
        return expected

    return _data


@pytest.fixture
def force_x86_64():
    # We have a different code path for arm to deal with LP1243287
    # We have to switch arch to x86_64 to avoid test failure
    force_arch("x86_64")
    yield
    # Return back to original arch
    force_arch()


@pytest.mark.usefixtures("fake_filesystem", "force_x86_64")
class TestGetCloudType:
    """Test to exercise method: DataSourceAltCloud.get_cloud_type()"""

    def test_cloud_info_file_ioerror(self, caplog, paths, tmp_path):
        """Return UNKNOWN when /etc/sysconfig/cloud-info exists but errors."""
        assert "/etc/sysconfig/cloud-info" == dsac.CLOUD_INFO_FILE
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        # Attempting to read the directory generates IOError
        with mock.patch.object(dsac, "CLOUD_INFO_FILE", str(tmp_path)):
            assert "UNKNOWN" == dsrc.get_cloud_type()
        assert "[Errno 21] Is a directory: '%s'" % tmp_path in caplog.text

    def test_cloud_info_file(self, paths):
        """Return uppercase stripped content from /etc/sysconfig/cloud-info."""
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        cloud_info = "cloud-info"
        util.write_file(cloud_info, " OverRiDdeN CloudType ")
        # Attempting to read the directory generates IOError
        with mock.patch.object(dsac, "CLOUD_INFO_FILE", cloud_info):
            assert "OVERRIDDEN CLOUDTYPE" == dsrc.get_cloud_type()

    def test_rhev(self, paths):
        """
        Test method get_cloud_type() for RHEVm systems.
        Forcing read_dmi_data return to match a RHEVm system: RHEV Hypervisor
        """
        dmi.read_dmi_data = _dmi_data("RHEV")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert "RHEV" == dsrc.get_cloud_type()

    def test_vsphere(self, paths):
        """
        Test method get_cloud_type() for vSphere systems.
        Forcing read_dmi_data return to match a vSphere system: RHEV Hypervisor
        """
        dmi.read_dmi_data = _dmi_data("VMware Virtual Platform")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert "VSPHERE" == dsrc.get_cloud_type()

    def test_unknown(self, paths):
        """
        Test method get_cloud_type() for unknown systems.
        Forcing read_dmi_data return to match an unrecognized return.
        """
        dmi.read_dmi_data = _dmi_data("Unrecognized Platform")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert "UNKNOWN" == dsrc.get_cloud_type()


@pytest.mark.usefixtures("fake_filesystem")
class TestGetDataCloudInfoFile:
    """
    Test to exercise method: DataSourceAltCloud.get_data()
    With a contrived CLOUD_INFO_FILE
    """

    CLOUD_INFO_FILE = "cloud-info"

    def test_rhev(self, paths):
        """Success Test module get_data() forcing RHEV."""

        util.write_file(self.CLOUD_INFO_FILE, "RHEV")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        dsrc.user_data_rhevm = lambda: True
        with mock.patch.object(dsac, "CLOUD_INFO_FILE", self.CLOUD_INFO_FILE):
            assert True is dsrc.get_data()
        assert "altcloud" == dsrc.cloud_name
        assert "altcloud" == dsrc.platform_type
        assert "rhev (/dev/fd0)" == dsrc.subplatform

    def test_vsphere(self, paths):
        """Success Test module get_data() forcing VSPHERE."""

        util.write_file(self.CLOUD_INFO_FILE, "VSPHERE")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        dsrc.user_data_vsphere = lambda: True
        with mock.patch.object(dsac, "CLOUD_INFO_FILE", self.CLOUD_INFO_FILE):
            assert True is dsrc.get_data()
        assert "altcloud" == dsrc.cloud_name
        assert "altcloud" == dsrc.platform_type
        assert "vsphere (unknown)" == dsrc.subplatform

    def test_fail_rhev(self, paths):
        """Failure Test module get_data() forcing RHEV."""

        util.write_file(self.CLOUD_INFO_FILE, "RHEV")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        dsrc.user_data_rhevm = lambda: False
        with mock.patch.object(dsac, "CLOUD_INFO_FILE", self.CLOUD_INFO_FILE):
            assert False is dsrc.get_data()

    def test_fail_vsphere(self, paths):
        """Failure Test module get_data() forcing VSPHERE."""

        util.write_file(self.CLOUD_INFO_FILE, "VSPHERE")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        dsrc.user_data_vsphere = lambda: False
        with mock.patch.object(dsac, "CLOUD_INFO_FILE", self.CLOUD_INFO_FILE):
            assert False is dsrc.get_data()

    def test_unrecognized(self, paths):
        """Failure Test module get_data() forcing unrecognized."""

        util.write_file(self.CLOUD_INFO_FILE, "unrecognized")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        with mock.patch.object(dsac, "CLOUD_INFO_FILE", self.CLOUD_INFO_FILE):
            assert False is dsrc.get_data()


@pytest.fixture
def fake_dsca_cloud_info():
    dsac.CLOUD_INFO_FILE = "no such file"
    yield
    dsac.CLOUD_INFO_FILE = "/etc/sysconfig/cloud-info"


@pytest.mark.usefixtures(
    "fake_filesystem", "force_x86_64", "fake_dsca_cloud_info"
)
class TestGetDataNoCloudInfoFile:
    """
    Test to exercise method: DataSourceAltCloud.get_data()
    Without a CLOUD_INFO_FILE
    """

    def test_rhev_no_cloud_file(self, paths):
        """Test No cloud info file module get_data() forcing RHEV."""

        dmi.read_dmi_data = _dmi_data("RHEV Hypervisor")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        dsrc.user_data_rhevm = lambda: True
        assert True is dsrc.get_data()

    def test_vsphere_no_cloud_file(self, paths):
        """Test No cloud info file module get_data() forcing VSPHERE."""

        dmi.read_dmi_data = _dmi_data("VMware Virtual Platform")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        dsrc.user_data_vsphere = lambda: True
        assert True is dsrc.get_data()

    def test_failure_no_cloud_file(self, paths):
        """Test No cloud info file module get_data() forcing unrecognized."""

        dmi.read_dmi_data = _dmi_data("Unrecognized Platform")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert False is dsrc.get_data()


@pytest.fixture
def user_data(tmp_path):
    mount_dir = str(tmp_path)
    _write_user_data_files(mount_dir, "test user data")
    yield
    _remove_user_data_files(mount_dir)
    # Attempt to remove the temp dir ignoring errors
    try:
        shutil.rmtree(mount_dir)
    except OSError:
        pass


@pytest.mark.usefixtures("user_data")
@mock.patch(
    "cloudinit.sources.DataSourceAltCloud.modprobe_floppy",
    return_value=None,
)
@mock.patch(
    "cloudinit.sources.DataSourceAltCloud.util.udevadm_settle",
    return_value=("", ""),
)
@mock.patch("cloudinit.sources.DataSourceAltCloud.util.mount_cb")
class TestUserDataRhevm:
    """
    Test to exercise method: DataSourceAltCloud.user_data_rhevm()
    """

    def test_mount_cb_fails(
        self, m_mount_cb, m_udevadm_settle, m_modprobe_floppy, paths
    ):
        """Test user_data_rhevm() where mount_cb fails."""
        m_mount_cb.side_effect = util.MountFailedError("Failed Mount")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert False is dsrc.user_data_rhevm()

    def test_modprobe_fails(
        self, m_mount_cb, m_udevadm_settle, m_modprobe_floppy, paths
    ):
        """Test user_data_rhevm() where modprobe fails."""
        m_modprobe_floppy.side_effect = subp.ProcessExecutionError(
            "Failed modprobe"
        )
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert False is dsrc.user_data_rhevm()

    def test_no_modprobe_cmd(
        self, m_mount_cb, m_udevadm_settle, m_modprobe_floppy, paths
    ):
        """Test user_data_rhevm() with no modprobe command."""
        m_modprobe_floppy.side_effect = subp.ProcessExecutionError(
            "No such file or dir"
        )
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert False is dsrc.user_data_rhevm()

    def test_udevadm_fails(
        self, m_mount_cb, m_udevadm_settle, m_modprobe_floppy, paths
    ):
        """Test user_data_rhevm() where udevadm fails."""
        m_udevadm_settle.side_effect = subp.ProcessExecutionError(
            "Failed settle."
        )
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert False is dsrc.user_data_rhevm()

    def test_no_udevadm_cmd(
        self, m_mount_cb, m_udevadm_settle, m_modprobe_floppy, paths
    ):
        """Test user_data_rhevm() with no udevadm command."""
        m_udevadm_settle.side_effect = OSError("No such file or dir")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert False is dsrc.user_data_rhevm()


@pytest.mark.usefixtures("user_data")
class TestUserDataVsphere:
    """
    Test to exercise method: DataSourceAltCloud.user_data_vsphere()
    """

    @mock.patch("cloudinit.sources.DataSourceAltCloud.util.find_devs_with")
    @mock.patch("cloudinit.sources.DataSourceAltCloud.util.mount_cb")
    def test_user_data_vsphere_no_cdrom(
        self, m_mount_cb, m_find_devs_with, paths
    ):
        """Test user_data_vsphere() where mount_cb fails."""

        m_mount_cb.return_value = []
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert False is dsrc.user_data_vsphere()
        assert 0 == m_mount_cb.call_count

    @mock.patch("cloudinit.sources.DataSourceAltCloud.util.find_devs_with")
    @mock.patch("cloudinit.sources.DataSourceAltCloud.util.mount_cb")
    def test_user_data_vsphere_mcb_fail(
        self, m_mount_cb, m_find_devs_with, paths
    ):
        """Test user_data_vsphere() where mount_cb fails."""

        m_find_devs_with.return_value = ["/dev/mock/cdrom"]
        m_mount_cb.side_effect = util.MountFailedError("Unable To mount")
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        assert False is dsrc.user_data_vsphere()
        assert 1 == m_find_devs_with.call_count
        assert 1 == m_mount_cb.call_count

    @mock.patch("cloudinit.sources.DataSourceAltCloud.util.find_devs_with")
    @mock.patch("cloudinit.sources.DataSourceAltCloud.util.mount_cb")
    def test_user_data_vsphere_success(
        self, m_mount_cb, m_find_devs_with, tmp_path, paths
    ):
        """Test user_data_vsphere() where successful."""
        m_find_devs_with.return_value = ["/dev/mock/cdrom"]
        m_mount_cb.return_value = "raw userdata from cdrom"
        dsrc = dsac.DataSourceAltCloud({}, None, paths)
        cloud_info = tmp_path / "cloud-info"
        util.write_file(cloud_info, "VSPHERE")
        assert True is dsrc.user_data_vsphere()
        m_find_devs_with.assert_called_once_with("LABEL=CDROM")
        m_mount_cb.assert_called_once_with(
            "/dev/mock/cdrom", dsac.read_user_data_callback
        )
        with mock.patch.object(dsrc, "get_cloud_type", return_value="VSPHERE"):
            assert "vsphere (/dev/mock/cdrom)" == dsrc.subplatform


@pytest.mark.usefixtures("user_data")
class TestReadUserDataCallback:
    """
    Test to exercise method: DataSourceAltCloud.read_user_data_callback()
    """

    def test_callback_both(self, tmp_path):
        """Test read_user_data_callback() with both files."""
        assert "test user data" == dsac.read_user_data_callback(str(tmp_path))

    def test_callback_dc(self, tmp_path):
        """Test read_user_data_callback() with only DC file."""
        _remove_user_data_files(str(tmp_path), dc_file=False, non_dc_file=True)
        assert "test user data" == dsac.read_user_data_callback(str(tmp_path))

    def test_callback_non_dc(self, tmp_path):
        """Test read_user_data_callback() with only non-DC file."""
        _remove_user_data_files(str(tmp_path), dc_file=True, non_dc_file=False)
        assert "test user data" == dsac.read_user_data_callback(str(tmp_path))

    def test_callback_none(self, tmp_path):
        """Test read_user_data_callback() no files are found."""
        _remove_user_data_files(str(tmp_path))
        assert dsac.read_user_data_callback(str(tmp_path)) is None


def force_arch(arch=None):
    def _os_uname():
        return ("LINUX", "NODENAME", "RELEASE", "VERSION", arch)

    if arch:
        setattr(os, "uname", _os_uname)
    elif arch is None:
        setattr(os, "uname", OS_UNAME_ORIG)
