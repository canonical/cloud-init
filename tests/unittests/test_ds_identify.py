# This file is part of cloud-init. See LICENSE file for license information.

import copy
import os
from collections import namedtuple
from logging import getLogger
from pathlib import Path
from tempfile import mkdtemp
from textwrap import dedent
from uuid import uuid4

import pytest
import yaml

from cloudinit import atomic_helper, subp, util
from cloudinit.sources import DataSourceIBMCloud as ds_ibm
from cloudinit.sources import DataSourceOracle as ds_oracle
from cloudinit.sources import DataSourceSmartOS as ds_smartos
from tests.helpers import cloud_init_project_dir
from tests.unittests.helpers import (
    CiTestCase,
    dir2dict,
    populate_dir,
    populate_dir_with_ts,
)

LOG = getLogger(__name__)

UNAME_MYSYS = "Linux #83-Ubuntu SMP Wed Jan 18 14:10:15 UTC 2017 x86_64"
UNAME_PPC64EL = (
    "Linux #106-Ubuntu SMP mon Jun 26 17:53:54 UTC 2017 "
    "ppc64le ppc64le ppc64le"
)
UNAME_FREEBSD = (
    "FreeBSD FreeBSD 14.0-RELEASE-p3 releng/14.0-n265398-20fae1e1699"
    "GENERIC-MMCCAM amd64"
)
UNAME_OPENBSD = "OpenBSD GENERIC.MP#1397 amd64"
UNAME_WSL = (
    "Linux 5.15.133.1-microsoft-standard-WSL2 #1 SMP Thu Oct 5 21:02:42 "
    "UTC 2023 x86_64"
)

BLKID_EFI_ROOT = """
DEVNAME=/dev/sda1
UUID=8B36-5390
TYPE=vfat
PARTUUID=30d7c715-a6ae-46ee-b050-afc6467fc452

DEVNAME=/dev/sda2
UUID=19ac97d5-6973-4193-9a09-2e6bbfa38262
TYPE=ext4
PARTUUID=30c65c77-e07d-4039-b2fb-88b1fb5fa1fc
"""

# this is a Ubuntu 18.04 disk.img output (dual uefi and bios bootable)
BLKID_UEFI_UBUNTU = [
    {"DEVNAME": "vda1", "TYPE": "ext4", "PARTUUID": uuid4(), "UUID": uuid4()},
    {"DEVNAME": "vda14", "PARTUUID": uuid4()},
    {
        "DEVNAME": "vda15",
        "TYPE": "vfat",
        "LABEL": "UEFI",
        "PARTUUID": uuid4(),
        "UUID": "5F55-129B",
    },
]


DEFAULT_CLOUD_CONFIG = """\
# The top level settings are used as module
# and base configuration.
# A set of users which may be applied and/or used by various modules
# when a 'default' entry is found it will reference the 'default_user'
# from the distro configuration specified below
users:
   - default

# If this is set, 'root' will not be able to ssh in and they
# will get a message to login instead as the default $user
disable_root: true

# This will cause the set+update hostname module to not operate (if true)
preserve_hostname: false

# If you use datasource_list array, keep array items in a single line.
# If you use multi line array, ds-identify script won't read array items.
# Example datasource config
# datasource:
#    Ec2:
#      metadata_urls: [ 'blah.com' ]
#      timeout: 5 # (defaults to 50 seconds)
#      max_wait: 10 # (defaults to 120 seconds)

# The modules that run in the 'init' stage
cloud_init_modules:
 - migrator
 - seed_random
 - bootcmd
 - write-files
 - growpart
 - resizefs
 - disk_setup
 - mounts
 - set_hostname
 - update_hostname
 - update_etc_hosts
 - ca-certs
 - rsyslog
 - users-groups
 - ssh

# The modules that run in the 'config' stage
cloud_config_modules:
 - wireguard
 - snap
 - ubuntu_autoinstall
 - ssh-import-id
 - keyboard
 - locale
 - set-passwords
 - grub-dpkg
 - apt-pipelining
 - apt-configure
 - ubuntu-advantage
 - ntp
 - timezone
 - disable-ec2-metadata
 - runcmd
 - byobu

# The modules that run in the 'final' stage
cloud_final_modules:
 - package-update-upgrade-install
 - fan
 - landscape
 - lxd
 - ubuntu-drivers
 - write-files-deferred
 - puppet
 - chef
 - ansible
 - mcollective
 - salt-minion
 - reset_rmc
 - refresh_rmc_and_interface
 - rightscale_userdata
 - scripts-vendor
 - scripts-per-once
 - scripts-per-boot
 - scripts-per-instance
 - scripts-user
 - ssh-authkey-fingerprints
 - keys-to-console
 - install-hotplug
 - phone-home
 - final-message
 - power-state-change

# System and/or distro specific settings
# (not accessible to handlers/transforms)
system_info:
   # This will affect which distro class gets used
   distro: ubuntu
   # Default user name + that default users groups (if added/used)
   default_user:
     name: ubuntu
     lock_passwd: True
     gecos: Ubuntu
     groups: [adm, audio, cdrom, floppy, lxd, netdev, plugdev, sudo, video]
     sudo: ["ALL=(ALL) NOPASSWD:ALL"]
     shell: /bin/bash
   network:
     renderers: ['netplan', 'eni', 'sysconfig']
     activators: ['netplan', 'eni', 'network-manager', 'networkd']
   # Automatically discover the best ntp_client
   ntp_client: auto
   # Other config here will be given to the distro class and/or path classes
   paths:
      cloud_dir: /var/lib/cloud/
      templates_dir: /etc/cloud/templates/
   package_mirrors:
     - arches: [i386, amd64]
       failsafe:
         primary: http://archive.ubuntu.com/ubuntu
         security: http://security.ubuntu.com/ubuntu
       search:
         primary:
           - http://%(ec2_region)s.ec2.archive.ubuntu.com/ubuntu/
           - http://%(availability_zone)s.clouds.archive.ubuntu.com/ubuntu/
           - http://%(region)s.clouds.archive.ubuntu.com/ubuntu/
         security: []
     - arches: [arm64, armel, armhf]
       failsafe:
         primary: http://ports.ubuntu.com/ubuntu-ports
         security: http://ports.ubuntu.com/ubuntu-ports
       search:
         primary:
           - http://%(ec2_region)s.ec2.ports.ubuntu.com/ubuntu-ports/
           - http://%(availability_zone)s.clouds.ports.ubuntu.com/ubuntu-ports/
           - http://%(region)s.clouds.ports.ubuntu.com/ubuntu-ports/
         security: []
     - arches: [default]
       failsafe:
         primary: http://ports.ubuntu.com/ubuntu-ports
         security: http://ports.ubuntu.com/ubuntu-ports
   ssh_svcname: ssh
"""

POLICY_FOUND_ONLY = "search,found=all,maybe=none,notfound=disabled"
POLICY_FOUND_OR_MAYBE = "search,found=all,maybe=all,notfound=disabled"
DI_DEFAULT_POLICY = "search,found=all,maybe=all,notfound=disabled"
DI_DEFAULT_POLICY_NO_DMI = "search,found=all,maybe=all,notfound=enabled"
DI_EC2_STRICT_ID_DEFAULT = "true"
OVF_MATCH_STRING = "http://schemas.dmtf.org/ovf/environment/1"

SHELL_MOCK_TMPL = """\
%(name)s() {
   local out='%(out)s' err='%(err)s' r='%(ret)s' RET='%(RET)s'
   [ "$out" = "_unset" ] || echo "$out"
   [ "$err" = "_unset" ] || echo "$err" 2>&1
   [ "$RET" = "_unset" ] || _RET="$RET"
   return $r
}
"""

RC_FOUND = 0
RC_NOT_FOUND = 1
DS_NONE = "None"

P_BOARD_NAME = "sys/class/dmi/id/board_name"
P_CHASSIS_ASSET_TAG = "sys/class/dmi/id/chassis_asset_tag"
P_PRODUCT_NAME = "sys/class/dmi/id/product_name"
P_PRODUCT_SERIAL = "sys/class/dmi/id/product_serial"
P_PRODUCT_UUID = "sys/class/dmi/id/product_uuid"
P_SYS_VENDOR = "sys/class/dmi/id/sys_vendor"
P_SEED_DIR = "var/lib/cloud/seed"
P_DSID_CFG = "etc/cloud/ds-identify.cfg"

IBM_CONFIG_UUID = "9796-932E"

MOCK_VIRT_IS_CONTAINER_OTHER = {
    "name": "detect_virt",
    "RET": "container-other",
    "ret": 0,
}
IS_CONTAINER_OTHER_ENV = {"SYSTEMD_VIRTUALIZATION": "vm:kvm"}
MOCK_NOT_LXD_DATASOURCE = {"name": "dscheck_LXD", "ret": 1}
MOCK_VIRT_IS_KVM = {"name": "detect_virt", "RET": "kvm", "ret": 0}
KVM_ENV = {"SYSTEMD_VIRTUALIZATION": "vm:kvm"}
# qemu support for LXD is only for host systems > 5.10 kernel as lxd
# passed `hv_passthrough` which causes systemd < v.251 to misinterpret CPU
# as "qemu" instead of "kvm"
MOCK_VIRT_IS_KVM_QEMU = {"name": "detect_virt", "RET": "qemu", "ret": 0}
IS_KVM_QEMU_ENV = {"SYSTEMD_VIRTUALIZATION": "vm:qemu"}
MOCK_VIRT_IS_VMWARE = {"name": "detect_virt", "RET": "vmware", "ret": 0}
IS_VMWARE_ENV = {"SYSTEMD_VIRTUALIZATION": "vm:vmware"}
# currenty' SmartOS hypervisor "bhyve" is unknown by systemd-detect-virt.
MOCK_VIRT_IS_VM_OTHER = {"name": "detect_virt", "RET": "vm-other", "ret": 0}
IS_VM_OTHER = {"SYSTEMD_VIRTUALIZATION": "vm:vm-other"}
MOCK_VIRT_IS_XEN = {"name": "detect_virt", "RET": "xen", "ret": 0}
IS_XEN_ENV = {"SYSTEMD_VIRTUALIZATION": "vm:xen"}
MOCK_VIRT_IS_WSL = {"name": "detect_virt", "RET": "wsl", "ret": 0}
MOCK_UNAME_IS_PPC64 = {"name": "uname", "out": UNAME_PPC64EL, "ret": 0}
MOCK_UNAME_IS_FREEBSD = {"name": "uname", "out": UNAME_FREEBSD, "ret": 0}
MOCK_UNAME_IS_OPENBSD = {"name": "uname", "out": UNAME_OPENBSD, "ret": 0}
MOCK_UNAME_IS_WSL = {"name": "uname", "out": UNAME_WSL, "ret": 0}
MOCK_WSL_INSTANCE_DATA = {
    "name": "Noble-MLKit",
    "distro": "ubuntu",
    "version": "24.04",
    "os_release": dedent(
        """\
        PRETTY_NAME="Ubuntu Noble Numbat (development branch)"
        NAME="Ubuntu"
        VERSION_ID="24.04"
        VERSION="24.04 (Noble Numbat)"
        VERSION_CODENAME=noble
        ID=ubuntu
        ID_LIKE=debian
        UBUNTU_CODENAME=noble
        LOGO=ubuntu-logo
        """
    ),
    "os_release_no_version_id": dedent(
        """\
        PRETTY_NAME="Debian GNU/Linux trixie/sid"
        NAME="Debian GNU/Linux"
        VERSION_CODENAME="trixie"
        ID=debian
        """
    ),
}

shell_true = 0
shell_false = 1

CallReturn = namedtuple(
    "CallReturn", ["rc", "stdout", "stderr", "cfg", "files"]
)


class DsIdentifyBase(CiTestCase):
    dsid_path = cloud_init_project_dir("tools/ds-identify")
    allowed_subp = ["sh"]

    # set to true to write out the mocked ds-identify for inspection
    debug_mode = True

    def call(
        self,
        rootd=None,
        mocks=None,
        no_mocks=None,
        func="main",
        args=None,
        files=None,
        policy_dmi=DI_DEFAULT_POLICY,
        policy_no_dmi=DI_DEFAULT_POLICY_NO_DMI,
        ec2_strict_id=DI_EC2_STRICT_ID_DEFAULT,
        env_vars=None,
    ):
        if args is None:
            args = []
        if mocks is None:
            mocks = []

        if files is None:
            files = {}

        cloudcfg = "etc/cloud/cloud.cfg"
        if cloudcfg not in files:
            files[cloudcfg] = DEFAULT_CLOUD_CONFIG

        if rootd is None:
            rootd = self.tmp_dir()

        unset = "_unset"
        wrap = self.tmp_path(path="_shwrap", dir=rootd)
        populate_dir(rootd, files)

        # DI_DEFAULT_POLICY* are declared always as to not rely
        # on the default in the code.  This is because SRU releases change
        # the value in the code, and thus tests would fail there.
        head = [
            "DI_MAIN=noop",
            "DEBUG_LEVEL=2",
            "DI_LOG=stderr",
            "PATH_ROOT='%s'" % rootd,
            ". " + self.dsid_path,
            'DI_DEFAULT_POLICY="%s"' % policy_dmi,
            'DI_DEFAULT_POLICY_NO_DMI="%s"' % policy_no_dmi,
            'DI_EC2_STRICT_ID_DEFAULT="%s"' % ec2_strict_id,
            "",
        ]

        def write_mock(data):
            ddata = {"out": None, "err": None, "ret": 0, "RET": None}
            ddata.update(data)
            for k in ddata.keys():
                if ddata[k] is None:
                    ddata[k] = unset
            return SHELL_MOCK_TMPL % ddata

        mocklines = []
        default_mocks = [
            MOCK_NOT_LXD_DATASOURCE,
            {"name": "detect_virt", "RET": "none", "ret": 1},
            {"name": "uname", "out": UNAME_MYSYS},
            {"name": "blkid", "out": BLKID_EFI_ROOT},
            {
                "name": "ovf_vmware_transport_guestinfo",
                "out": "No value found",
                "ret": 1,
            },
            {
                "name": "dmi_decode",
                "ret": 1,
                "err": "No dmidecode program. ERROR.",
            },
            {
                "name": "is_disabled",
                "ret": 1,
            },
            {
                "name": "get_kenv_field",
                "ret": 1,
                "err": "No kenv program. ERROR.",
            },
        ]

        uname = "Linux"
        runpath = "run"
        written = []
        for d in mocks:
            written.append(d["name"])
            if d["name"] == "uname":
                uname = d["out"].split(" ")[0]
        # set runpath so that BSDs use /var/run rather than /run
        if uname != "Linux":
            runpath = "var/run"

        for data in mocks:
            mocklines.append(write_mock(data))
        for d in default_mocks:
            if no_mocks and d["name"] in no_mocks:
                continue
            if d["name"] not in written:
                mocklines.append(write_mock(d))

        endlines = [func + " " + " ".join(['"%s"' % s for s in args])]

        mocked_ds_identify = "\n".join(head + mocklines + endlines) + "\n"
        with open(wrap, "w") as fp:
            fp.write(mocked_ds_identify)

        # debug_mode force this test to write the mocked ds-identify script to
        # a file for inspection
        if self.debug_mode:
            tempdir = mkdtemp()
            dir = f"{tempdir}/ds-identify"
            LOG.debug("Writing mocked ds-identify to %s for debugging.", dir)
            with open(dir, "w") as fp:
                fp.write(mocked_ds_identify)

        rc = 0
        try:
            out, err = subp.subp(
                ["sh", "-c", ". %s" % wrap],
                update_env=env_vars if env_vars else {},
                capture=True,
            )
        except subp.ProcessExecutionError as e:
            rc = e.exit_code
            out = e.stdout
            err = e.stderr

        cfg = None
        cfg_out = os.path.join(rootd, runpath, "cloud-init/cloud.cfg")
        if os.path.exists(cfg_out):
            contents = util.load_text_file(cfg_out)
            try:
                cfg = yaml.safe_load(contents)
            except Exception as e:
                cfg = {"_INVALID_YAML": contents, "_EXCEPTION": str(e)}

        return CallReturn(rc, out, err, cfg, dir2dict(rootd))

    def _call_via_dict(self, data, rootd=None, **kwargs):
        # return output of self.call with a dict input like VALID_CFG[item]
        xwargs = {"rootd": rootd}
        passthrough = (
            "no_mocks",  # named mocks to ignore
            "mocks",
            "func",
            "args",
            "env_vars",
            "policy_dmi",
            "policy_no_dmi",
            "files",
        )
        for k in passthrough:
            if k in data:
                xwargs[k] = data[k]
            if k in kwargs:
                xwargs[k] = kwargs[k]
        return self.call(**xwargs)

    def _test_ds_found(self, name):
        data = copy.deepcopy(VALID_CFG[name])

        return self._check_via_dict(
            data, RC_FOUND, dslist=[data.pop("ds"), DS_NONE]
        )

    def _test_ds_not_found(self, name):
        data = copy.deepcopy(VALID_CFG[name])
        return self._check_via_dict(data, RC_NOT_FOUND)

    def _check_via_dict(self, data, rc, dslist=None, **kwargs):
        ret = self._call_via_dict(data, **kwargs)
        good = False
        try:
            self.assertEqual(rc, ret.rc)
            if dslist is not None:
                self.assertEqual(dslist, ret.cfg.get("datasource_list"))
            good = True
        finally:
            if not good:
                _print_run_output(
                    ret.rc, ret.stdout, ret.stderr, ret.cfg, ret.files
                )
        return ret


class TestDsIdentify(DsIdentifyBase):
    def test_wb_print_variables(self):
        """_print_info reports an array of discovered variables to stderr."""
        data = VALID_CFG["Azure-dmi-detection"]
        _, _, err, _, _ = self._call_via_dict(data)
        expected_vars = [
            "DMI_PRODUCT_NAME",
            "DMI_SYS_VENDOR",
            "DMI_PRODUCT_SERIAL",
            "DMI_PRODUCT_UUID",
            "PID_1_PRODUCT_NAME",
            "DMI_CHASSIS_ASSET_TAG",
            "FS_LABELS",
            "KERNEL_CMDLINE",
            "VIRT",
            "UNAME_KERNEL_NAME",
            "UNAME_KERNEL_VERSION",
            "UNAME_MACHINE",
            "DSNAME",
            "DSLIST",
            "MODE",
            "ON_FOUND",
            "ON_MAYBE",
            "ON_NOTFOUND",
        ]
        for var in expected_vars:
            self.assertIn("{0}=".format(var), err)

    @pytest.mark.xfail(reason="GH-4796")
    def test_maas_not_detected_1(self):
        """Don't incorrectly identify maas

        In ds-identify the function check_config() attempts to parse yaml keys
        in bash, but it sometimes introduces false positives. The maas
        datasource uses check_config() and the existence of a "MAAS" key to
        identify itself (which is a very poor identifier - clouds should have
        stricter identifiers). Since the MAAS datasource is at the begining of
        the list, this is particularly troublesome and more concerning than
        NoCloud false positives, for example.
        """
        config = "LXD-kvm-not-MAAS-1"
        self._test_ds_found(config)

    def test_maas_not_detected_2(self):
        """Don't incorrectly identify maas

        The bug reported in 4794 combined with the previously existing bug
        reported in 4796 made for very loose MAAS false-positives.

        In ds-identify the function check_config() attempts to parse yaml keys
        in bash, but it sometimes introduces false positives. The maas
        datasource uses check_config() and the existence of a "MAAS" key to
        identify itself (which is a very poor identifier - clouds should have
        stricter identifiers). Since the MAAS datasource is at the begining of
        the list, this is particularly troublesome and more concerning than
        NoCloud false positives, for example.
        """
        config = "LXD-kvm-not-MAAS-2"
        self._test_ds_found(config)

    @pytest.mark.xfail(reason="GH-4796")
    def test_maas_not_detected_3(self):
        """Don't incorrectly identify maas

        The bug reported in 4794 combined with the previously existing bug
        reported in 4796 made for very loose MAAS false-positives.

        In ds-identify the function check_config() attempts to parse yaml keys
        in bash, but it sometimes introduces false positives. The maas
        datasource uses check_config() and the existence of a "MAAS" key to
        identify itself (which is a very poor identifier - clouds should have
        stricter identifiers). Since the MAAS datasource is at the begining of
        the list, this is particularly troublesome and more concerning than
        NoCloud false positives, for example.
        """
        config = "LXD-kvm-not-MAAS-3"
        self._test_ds_found(config)

    def test_flow_sequence_control(self):
        """ensure that an invalid key in the flow_sequence tests produces no
        datasource list match

        control test: this test serves as a control test for test_flow_sequence
        """
        data = copy.deepcopy(VALID_CFG["flow_sequence-control"])
        self._check_via_dict(data, RC_NOT_FOUND)

    def test_flow_sequence(self):
        """correctly identify flow sequences"""
        for i in range(1, 10):
            data = copy.deepcopy(VALID_CFG[f"flow_sequence-{i}"])
            self._check_via_dict(data, RC_FOUND, dslist=[data.get("ds")])

    def test_azure_invalid_configuration(self):
        """Don't detect incorrect config when invalid datasource_list provided

        If unparsable list is provided we just ignore it. Some users
        might assume that since the rest of the configuration is yaml that
        multi-line yaml lists are valid (they aren't). When this happens, just
        run ds-identify and figure it out for ourselves which platform to run.
        """
        self._test_ds_found("Azure-parse-invalid")

    def test_azure_dmi_detection_from_chassis_asset_tag(self):
        """Azure datasource is detected from DMI chassis-asset-tag"""
        self._test_ds_found("Azure-dmi-detection")

    def test_azure_seed_file_detection(self):
        """Azure datasource is detected due to presence of a seed file.

        The seed file tested  is /var/lib/cloud/seed/azure/ovf-env.xml."""
        self._test_ds_found("Azure-seed-detection")

    def test_aws_ec2_hvm(self):
        """EC2: hvm instances use dmi serial and uuid starting with 'ec2'."""
        self._test_ds_found("Ec2-hvm")

    def test_aws_ec2_hvm_env(self):
        """EC2: hvm instances use dmi serial and uuid starting with 'ec2'

        test using SYSTEMD_VIRTUALIZATION, not systemd-detect-virt
        """
        self._test_ds_found("Ec2-hvm-env")

    def test_aws_ec2_hvm_endian(self):
        """EC2: hvm instances use system-uuid and may have swapped endianness

        test using SYSTEMD_VIRTUALIZATION, not systemd-detect-virt
        """
        self._test_ds_found("Ec2-hvm-swap-endianness")

    def test_aws_ec2_xen(self):
        """EC2: sys/hypervisor/uuid starts with ec2."""
        self._test_ds_found("Ec2-xen")

    def test_brightbox_is_ec2(self):
        """EC2: product_serial ends with '.brightbox.com'"""
        self._test_ds_found("Ec2-brightbox")

    def test_bobrightbox_is_not_brightbox(self):
        """EC2: bobrightbox.com in product_serial is not brightbox'"""
        self._test_ds_not_found("Ec2-brightbox-negative")

    def test_freebsd_nocloud(self):
        """NoCloud identified on FreeBSD via label by geom."""
        self._test_ds_found("NoCloud-fbsd")

    def test_gce_by_product_name(self):
        """GCE identifies itself with product_name."""
        self._test_ds_found("GCE")

    def test_gce_by_product_name_env(self):
        """GCE identifies itself with product_name.

        Uses SYSTEMD_VIRTUALIZATION
        """
        self._test_ds_found("GCE_ENV")

    def test_gce_by_serial(self):
        """Older gce compute instances must be identified by serial."""
        self._test_ds_found("GCE-serial")

    def test_lxd_kvm(self):
        """LXD KVM has race on absent /dev/lxd/socket. Use DMI board_name."""
        self._test_ds_found("LXD-kvm")

    def test_lxd_kvm_jammy(self):
        """LXD KVM on host systems with a kernel > 5.10 need to match "qemu".
        LXD provides `hv_passthrough` when launching kvm instances when host
        kernel is > 5.10. This results in systemd being unable to detect the
        virtualized CPUID="Linux KVM Hv" as type "kvm" and results in
        systemd-detect-virt returning "qemu" in this case.

        Assert ds-identify can match systemd-detect-virt="qemu" and
        /sys/class/dmi/id/board_name = LXD.
        Once systemd 251 is available on a target distro, the virtualized
        CPUID will be represented properly as "kvm"
        """
        self._test_ds_found("LXD-kvm-qemu-kernel-gt-5.10")

    def test_lxd_kvm_jammy_env(self):
        """LXD KVM on host systems with a kernel > 5.10 need to match "qemu".
        LXD provides `hv_passthrough` when launching kvm instances when host
        kernel is > 5.10. This results in systemd being unable to detect the
        virtualized CPUID="Linux KVM Hv" as type "kvm" and results in
        systemd-detect-virt returning "qemu" in this case.

        Assert ds-identify can match systemd-detect-virt="qemu" and
        /sys/class/dmi/id/board_name = LXD.
        Once systemd 251 is available on a target distro, the virtualized
        CPUID will be represented properly as "kvm"
        """
        self._test_ds_found("LXD-kvm-qemu-kernel-gt-5.10-env")

    def test_lxd_containers(self):
        """LXD containers will have /dev/lxd/socket at generator time."""
        self._test_ds_found("LXD")

    def test_config_drive(self):
        """ConfigDrive datasource has a disk with LABEL=config-2."""
        self._test_ds_found("ConfigDrive")

    def test_rbx_cloud(self):
        """Rbx datasource has a disk with LABEL=CLOUDMD."""
        self._test_ds_found("RbxCloud")

    def test_rbx_cloud_lower(self):
        """Rbx datasource has a disk with LABEL=cloudmd."""
        self._test_ds_found("RbxCloudLower")

    def test_config_drive_upper(self):
        """ConfigDrive datasource has a disk with LABEL=CONFIG-2."""
        self._test_ds_found("ConfigDriveUpper")

    def test_config_drive_seed(self):
        """Config Drive seed directory."""
        self._test_ds_found("ConfigDrive-seed")

    def test_config_drive_interacts_with_ibmcloud_config_disk(self):
        """Verify ConfigDrive interaction with IBMCloud.

        If ConfigDrive is enabled and not IBMCloud, then ConfigDrive
        should claim the ibmcloud 'config-2' disk.
        If IBMCloud is enabled, then ConfigDrive should skip."""
        data = copy.deepcopy(VALID_CFG["IBMCloud-config-2"])
        files = data.get("files", {})
        if not files:
            data["files"] = files
        cfgpath = "etc/cloud/cloud.cfg.d/99_networklayer_common.cfg"

        # with list including IBMCloud, config drive should be not found.
        files[cfgpath] = "datasource_list: [ ConfigDrive, IBMCloud ]\n"
        ret = self._check_via_dict(data, shell_true)
        self.assertEqual(ret.cfg.get("datasource_list"), ["IBMCloud", "None"])

        # But if IBMCloud is not enabled, config drive should claim this.
        files[cfgpath] = "datasource_list: [ ConfigDrive, NoCloud ]\n"
        ret = self._check_via_dict(data, shell_true)
        self.assertEqual(
            ret.cfg.get("datasource_list"), ["ConfigDrive", "None"]
        )

    @pytest.mark.xfail(
        reason=("not supported: yaml parser implemented in POSIX shell")
    )
    def test_multiline_yaml(self):
        """Multi-line yaml is unsupported"""
        self._test_ds_found("LXD-kvm-not-azure")

    def test_ibmcloud_template_userdata_in_provisioning(self):
        """Template provisioned with user-data during provisioning stage.

        Template provisioning with user-data has METADATA disk,
        datasource should return not found."""
        data = copy.deepcopy(VALID_CFG["IBMCloud-metadata"])
        # change the 'is_ibm_provisioning' mock to return 1 (false)
        isprov_m = [
            m for m in data["mocks"] if m["name"] == "is_ibm_provisioning"
        ][0]
        isprov_m["ret"] = shell_true
        return self._check_via_dict(data, RC_NOT_FOUND)

    def test_ibmcloud_template_userdata(self):
        """Template provisioned with user-data first boot.

        Template provisioning with user-data has METADATA disk.
        datasource should return found."""
        self._test_ds_found("IBMCloud-metadata")

    def test_ibmcloud_template_no_userdata_in_provisioning(self):
        """Template provisioned with no user-data during provisioning.

        no disks attached.  Datasource should return not found."""
        data = copy.deepcopy(VALID_CFG["IBMCloud-nodisks"])
        data["mocks"].append(
            {"name": "is_ibm_provisioning", "ret": shell_true}
        )
        return self._check_via_dict(data, RC_NOT_FOUND)

    def test_ibmcloud_template_no_userdata(self):
        """Template provisioned with no user-data first boot.

        no disks attached.  Datasource should return found."""
        self._check_via_dict(VALID_CFG["IBMCloud-nodisks"], RC_NOT_FOUND)

    def test_ibmcloud_os_code(self):
        """Launched by os code always has config-2 disk."""
        self._test_ds_found("IBMCloud-config-2")

    def test_ibmcloud_os_code_different_uuid(self):
        """IBM cloud config-2 disks must be explicit match on UUID.

        If the UUID is not 9796-932E then we actually expect ConfigDrive."""
        data = copy.deepcopy(VALID_CFG["IBMCloud-config-2"])
        offset = None
        for m, d in enumerate(data["mocks"]):
            if d.get("name") == "blkid":
                offset = m
                break
        if not offset:
            raise ValueError("Expected to find 'blkid' mock, but did not.")
        data["mocks"][offset]["out"] = d["out"].replace(
            ds_ibm.IBM_CONFIG_UUID, "DEAD-BEEF"
        )
        self._check_via_dict(
            data, rc=RC_FOUND, dslist=["ConfigDrive", DS_NONE]
        )

    def test_ibmcloud_with_nocloud_seed(self):
        """NoCloud seed should be preferred over IBMCloud.

        A nocloud seed should be preferred over IBMCloud even if enabled.
        Ubuntu 16.04 images have <vlc>/seed/nocloud-net. LP: #1766401."""
        data = copy.deepcopy(VALID_CFG["IBMCloud-config-2"])
        files = data.get("files", {})
        if not files:
            data["files"] = files
        files.update(VALID_CFG["NoCloud-seed"]["files"])
        ret = self._check_via_dict(data, shell_true)
        self.assertEqual(
            ["NoCloud", "IBMCloud", "None"], ret.cfg.get("datasource_list")
        )

    def test_ibmcloud_with_configdrive_seed(self):
        """ConfigDrive seed should be preferred over IBMCloud.

        A ConfigDrive seed should be preferred over IBMCloud even if enabled.
        Ubuntu 16.04 images have a fstab entry that mounts the
        METADATA disk into <vlc>/seed/config_drive. LP: ##1766401."""
        data = copy.deepcopy(VALID_CFG["IBMCloud-config-2"])
        files = data.get("files", {})
        if not files:
            data["files"] = files
        files.update(VALID_CFG["ConfigDrive-seed"]["files"])
        ret = self._check_via_dict(data, shell_true)
        self.assertEqual(
            ["ConfigDrive", "IBMCloud", "None"], ret.cfg.get("datasource_list")
        )

    def test_policy_disabled(self):
        """A Builtin policy of 'disabled' should return not found.

        Even though a search would find something, the builtin policy of
        disabled should cause the return of not found."""
        mydata = copy.deepcopy(VALID_CFG["Ec2-hvm"])
        self._check_via_dict(mydata, rc=RC_NOT_FOUND, policy_dmi="disabled")

    def test_policy_config_disable_overrides_builtin(self):
        """explicit policy: disabled in config file should cause not found."""
        mydata = copy.deepcopy(VALID_CFG["Ec2-hvm"])
        mydata["files"][P_DSID_CFG] = "\n".join(["policy: disabled", ""])
        self._check_via_dict(mydata, rc=RC_NOT_FOUND)

    def test_single_entry_defines_datasource(self):
        """If config has a single entry in datasource_list, that is used.

        Test the valid Ec2-hvm, but provide a config file that specifies
        a single entry in datasource_list.  The configured value should
        be used."""
        mydata = copy.deepcopy(VALID_CFG["Ec2-hvm"])
        cfgpath = "etc/cloud/cloud.cfg.d/myds.cfg"
        mydata["files"][cfgpath] = 'datasource_list: ["NoCloud"]\n'
        self._check_via_dict(mydata, rc=RC_FOUND, dslist=["NoCloud"])

    def test_configured_list_with_none(self):
        """When datasource_list already contains None, None is not added.

        The explicitly configured datasource_list has 'None' in it.  That
        should not have None automatically added."""
        mydata = copy.deepcopy(VALID_CFG["GCE"])
        cfgpath = "etc/cloud/cloud.cfg.d/myds.cfg"
        mydata["files"][cfgpath] = 'datasource_list: ["Ec2", "None"]\n'
        self._check_via_dict(mydata, rc=RC_FOUND, dslist=["Ec2", DS_NONE])

    def test_aliyun_identified(self):
        """Test that Aliyun cloud is identified by product id."""
        self._test_ds_found("AliYun")

    def test_aliyun_over_ec2(self):
        """Even if all other factors identified Ec2, AliYun should be used."""
        mydata = copy.deepcopy(VALID_CFG["Ec2-xen"])
        self._test_ds_found("AliYun")
        prod_name = VALID_CFG["AliYun"]["files"][P_PRODUCT_NAME]
        mydata["files"][P_PRODUCT_NAME] = prod_name
        policy = "search,found=first,maybe=none,notfound=disabled"
        self._check_via_dict(
            mydata, rc=RC_FOUND, dslist=["AliYun", DS_NONE], policy_dmi=policy
        )

    def test_default_openstack_intel_is_found(self):
        """On Intel, openstack must be identified."""
        self._test_ds_found("OpenStack")

    def test_openstack_open_telekom_cloud(self):
        """Open Telecom identification."""
        self._test_ds_found("OpenStack-OpenTelekom")

    def test_openstack_sap_ccloud(self):
        """SAP Converged Cloud identification"""
        self._test_ds_found("OpenStack-SAPCCloud")

    def test_openstack_sap_ccloud_env(self):
        """SAP Converged Cloud identification"""
        self._test_ds_found("OpenStack-SAPCCloud-env")

    def test_openstack_huawei_cloud(self):
        """Open Huawei Cloud identification."""
        self._test_ds_found("OpenStack-HuaweiCloud")

    def test_openstack_asset_tag_nova(self):
        """OpenStack identification via asset tag OpenStack Nova."""
        self._test_ds_found("OpenStack-AssetTag-Nova")

    def test_openstack_asset_tag_copute(self):
        """OpenStack identification via asset tag OpenStack Compute."""
        self._test_ds_found("OpenStack-AssetTag-Compute")

    def test_openstack_on_non_intel_is_maybe(self):
        """On non-Intel, openstack without dmi info is maybe.

        nova does not identify itself on platforms other than intel.
        https://bugs.launchpad.net/cloud-init/+bugs?field.tag=dsid-nova"""

        data = copy.deepcopy(VALID_CFG["OpenStack"])
        del data["files"][P_PRODUCT_NAME]
        data.update(
            {
                "policy_dmi": POLICY_FOUND_OR_MAYBE,
                "policy_no_dmi": POLICY_FOUND_OR_MAYBE,
            }
        )

        # this should show not found as default uname in tests is intel.
        # and intel openstack requires positive identification.
        self._check_via_dict(data, RC_NOT_FOUND, dslist=None)

        # updating the uname to ppc64 though should get a maybe.
        data.update({"mocks": [MOCK_VIRT_IS_KVM, MOCK_UNAME_IS_PPC64]})
        (_, _, err, _, _) = self._check_via_dict(
            data, RC_FOUND, dslist=["OpenStack", "None"]
        )
        self.assertIn("check for 'OpenStack' returned maybe", err)

    def test_default_ovf_is_found(self):
        """OVF is identified found when ovf/ovf-env.xml seed file exists."""
        self._test_ds_found("OVF-seed")

    def test_default_ovf_with_detect_virt_none_not_found(self):
        """OVF identifies not found when detect_virt returns "none"."""
        self._check_via_dict(
            {"ds": "OVF"}, rc=RC_NOT_FOUND, policy_dmi="disabled"
        )

    def test_default_ovf_returns_not_found_on_azure(self):
        """OVF datasource won't be found as false positive on Azure."""
        ovfonazure = copy.deepcopy(VALID_CFG["OVF"])
        # Set azure asset tag to assert OVF content not found
        ovfonazure["files"][
            P_CHASSIS_ASSET_TAG
        ] = "7783-7084-3265-9085-8269-3286-77\n"
        self._check_via_dict(ovfonazure, RC_FOUND, dslist=["Azure", DS_NONE])

    def test_ovf_on_vmware_iso_found_by_cdrom_with_ovf_schema_match(self):
        """OVF is identified when iso9660 cdrom path contains ovf schema."""
        self._test_ds_found("OVF")

    def test_ovf_on_vmware_guestinfo_found(self):
        """OVF guest info is found on vmware."""
        self._test_ds_found("OVF-guestinfo")

    def test_ovf_on_vmware_iso_found_by_cdrom_with_matching_fs_label(self):
        """OVF is identified by well-known iso9660 labels."""
        ovf_cdrom_by_label = copy.deepcopy(VALID_CFG["OVF"])
        # Unset matching cdrom ovf schema content
        ovf_cdrom_by_label["files"]["dev/sr0"] = "No content match"
        self._check_via_dict(
            ovf_cdrom_by_label, rc=RC_NOT_FOUND, policy_dmi="disabled"
        )

        # Add recognized labels
        valid_ovf_labels = [
            "ovf-transport",
            "OVF-TRANSPORT",
            "OVFENV",
            "ovfenv",
            "OVF ENV",
            "ovf env",
        ]
        for valid_ovf_label in valid_ovf_labels:
            ovf_cdrom_by_label["mocks"][0]["out"] = blkid_out(
                [
                    {"DEVNAME": "sda1", "TYPE": "ext4", "LABEL": "rootfs"},
                    {
                        "DEVNAME": "sr0",
                        "TYPE": "iso9660",
                        "LABEL": valid_ovf_label,
                    },
                    {"DEVNAME": "vda1", "TYPE": "ntfs", "LABEL": "data"},
                ]
            )
            self._check_via_dict(
                ovf_cdrom_by_label, rc=RC_FOUND, dslist=["OVF", DS_NONE]
            )

    def test_ovf_on_vmware_iso_found_by_cdrom_with_different_size(self):
        """OVF is identified by well-known iso9660 labels."""
        ovf_cdrom_with_size = copy.deepcopy(VALID_CFG["OVF"])

        # Set cdrom size to 20480 (10MB in 512 byte units)
        ovf_cdrom_with_size["files"]["sys/class/block/sr0/size"] = "20480\n"
        self._check_via_dict(
            ovf_cdrom_with_size, rc=RC_NOT_FOUND, policy_dmi="disabled"
        )

        # Set cdrom size to 204800 (100MB in 512 byte units)
        ovf_cdrom_with_size["files"]["sys/class/block/sr0/size"] = "204800\n"
        self._check_via_dict(
            ovf_cdrom_with_size, rc=RC_NOT_FOUND, policy_dmi="disabled"
        )

        # Set cdrom size to 18432 (9MB in 512 byte units)
        ovf_cdrom_with_size["files"]["sys/class/block/sr0/size"] = "18432\n"
        self._check_via_dict(
            ovf_cdrom_with_size, rc=RC_FOUND, dslist=["OVF", DS_NONE]
        )

        # Set cdrom size to 2048 (1MB in 512 byte units)
        ovf_cdrom_with_size["files"]["sys/class/block/sr0/size"] = "2048\n"
        self._check_via_dict(
            ovf_cdrom_with_size, rc=RC_FOUND, dslist=["OVF", DS_NONE]
        )

    def test_default_nocloud_as_vdb_iso9660(self):
        """NoCloud is found with iso9660 filesystem on non-cdrom disk."""
        self._test_ds_found("NoCloud")

    def test_nocloud_upper(self):
        """NoCloud is found with uppercase filesystem label."""
        self._test_ds_found("NoCloudUpper")

    def test_nocloud_seed_in_cfg(self):
        """NoCloud seed definition can go in /etc/cloud/cloud.cfg[.d]"""
        self._test_ds_found("NoCloud-cfg")

    def test_nocloud_fatboot(self):
        """NoCloud fatboot label - LP: #184166."""
        self._test_ds_found("NoCloud-fatboot")

    def test_nocloud_seed(self):
        """Nocloud seed directory."""
        self._test_ds_found("NoCloud-seed")

    def test_nocloud_seed_ubuntu_core_writable(self):
        """Nocloud seed directory ubuntu core writable"""
        self._test_ds_found("NoCloud-seed-ubuntu-core")

    def test_hetzner_found(self):
        """Hetzner cloud is identified in sys_vendor."""
        self._test_ds_found("Hetzner")

    def test_nwcs_found(self):
        """NWCS is identified in sys_vendor."""
        self._test_ds_found("NWCS")

    def test_smartos_bhyve(self):
        """SmartOS cloud identified by SmartDC in dmi."""
        self._test_ds_found("SmartOS-bhyve")

    def test_smartos_lxbrand(self):
        """SmartOS cloud identified on lxbrand container."""
        self._test_ds_found("SmartOS-lxbrand")

    def test_smartos_lxbrand_env(self):
        """SmartOS cloud identified on lxbrand container."""
        self._test_ds_found("SmartOS-lxbrand-env")

    def test_smartos_lxbrand_requires_socket(self):
        """SmartOS cloud should not be identified if no socket file."""
        mycfg = copy.deepcopy(VALID_CFG["SmartOS-lxbrand"])
        del mycfg["files"][ds_smartos.METADATA_SOCKFILE]
        self._check_via_dict(mycfg, rc=RC_NOT_FOUND, policy_dmi="disabled")

    def test_smartos_lxbrand_requires_socket_env(self):
        """SmartOS cloud should not be identified if no socket file."""
        mycfg = copy.deepcopy(VALID_CFG["SmartOS-lxbrand-env"])
        del mycfg["files"][ds_smartos.METADATA_SOCKFILE]
        self._check_via_dict(mycfg, rc=RC_NOT_FOUND, policy_dmi="disabled")

    def test_path_env_gets_set_from_main(self):
        """PATH environment should always have some tokens when main is run.

        We explicitly call main as we want to ensure it updates PATH."""
        cust = copy.deepcopy(VALID_CFG["NoCloud"])
        rootd = self.tmp_dir()
        mpp = "main-printpath"
        pre = "MYPATH="
        cust["files"][mpp] = (
            'PATH="/mycust/path"; main; r=$?; echo ' + pre + "$PATH; exit $r;"
        )
        ret = self._check_via_dict(
            cust,
            RC_FOUND,
            func=".",
            args=[os.path.join(rootd, mpp)],
            rootd=rootd,
        )
        match = [
            line for line in ret.stdout.splitlines() if line.startswith(pre)
        ][0]
        toks = match.replace(pre, "").split(":")
        expected = ["/sbin", "/bin", "/usr/sbin", "/usr/bin", "/mycust/path"]
        self.assertEqual(
            expected,
            [p for p in expected if p in toks],
            "path did not have expected tokens",
        )

    def test_zstack_is_ec2(self):
        """EC2: chassis asset tag ends with 'zstack.io'"""
        self._test_ds_found("Ec2-ZStack")

    def test_e24cloud_is_ec2(self):
        """EC2: e24cloud identified by sys_vendor"""
        self._test_ds_found("Ec2-E24Cloud")

    def test_e24cloud_not_active(self):
        """EC2: bobrightbox.com in product_serial is not brightbox'"""
        self._test_ds_not_found("Ec2-E24Cloud-negative")

    def test_outscale_is_ec2(self):
        """EC2: outscale identified by sys_vendor and product_name"""
        self._test_ds_found("Ec2-Outscale")

    def test_outscale_not_active_sysvendor(self):
        """EC2: outscale in sys_vendor is not outscale'"""
        self._test_ds_not_found("Ec2-Outscale-negative-sysvendor")

    def test_outscale_not_active_productname(self):
        """EC2: outscale in product_name is not outscale'"""
        self._test_ds_not_found("Ec2-Outscale-negative-productname")

    def test_vmware_no_valid_transports(self):
        """VMware: no valid transports"""
        self._test_ds_not_found("VMware-NoValidTransports")

    def test_vmware_on_vmware_when_vmware_customization_is_enabled(self):
        """VMware is identified when vmware customization is enabled."""
        self._test_ds_found("VMware-vmware-customization")

    def test_vmware_on_vmware_open_vm_tools_64(self):
        """VMware is identified when open-vm-tools installed in /usr/lib64."""
        cust64 = copy.deepcopy(VALID_CFG["VMware-vmware-customization"])
        p32 = "usr/lib/vmware-tools/plugins/vmsvc/libdeployPkgPlugin.so"
        open64 = "usr/lib64/open-vm-tools/plugins/vmsvc/libdeployPkgPlugin.so"
        cust64["files"][open64] = cust64["files"][p32]
        del cust64["files"][p32]
        return self._check_via_dict(
            cust64, RC_FOUND, dslist=[cust64.get("ds"), DS_NONE]
        )

    def test_vmware_on_vmware_open_vm_tools_x86_64_linux_gnu(self):
        """VMware is identified when open-vm-tools installed in
        /usr/lib/x86_64-linux-gnu."""
        cust64 = copy.deepcopy(VALID_CFG["VMware-vmware-customization"])
        p32 = "usr/lib/vmware-tools/plugins/vmsvc/libdeployPkgPlugin.so"
        x86 = (
            "usr/lib/x86_64-linux-gnu/open-vm-tools/plugins/vmsvc/"
            "libdeployPkgPlugin.so"
        )
        cust64["files"][x86] = cust64["files"][p32]
        del cust64["files"][p32]
        return self._check_via_dict(
            cust64, RC_FOUND, dslist=[cust64.get("ds"), DS_NONE]
        )

    def test_vmware_on_vmware_open_vm_tools_aarch64_linux_gnu(self):
        """VMware is identified when open-vm-tools installed in
        /usr/lib/aarch64-linux-gnu."""
        cust64 = copy.deepcopy(VALID_CFG["VMware-vmware-customization"])
        p32 = "usr/lib/vmware-tools/plugins/vmsvc/libdeployPkgPlugin.so"
        aarch64 = (
            "usr/lib/aarch64-linux-gnu/open-vm-tools/plugins/vmsvc/"
            "libdeployPkgPlugin.so"
        )
        cust64["files"][aarch64] = cust64["files"][p32]
        del cust64["files"][p32]
        return self._check_via_dict(
            cust64, RC_FOUND, dslist=[cust64.get("ds"), DS_NONE]
        )

    def test_vmware_on_vmware_open_vm_tools_i386_linux_gnu(self):
        """VMware is identified when open-vm-tools installed in
        /usr/lib/i386-linux-gnu."""
        cust64 = copy.deepcopy(VALID_CFG["VMware-vmware-customization"])
        p32 = "usr/lib/vmware-tools/plugins/vmsvc/libdeployPkgPlugin.so"
        i386 = (
            "usr/lib/i386-linux-gnu/open-vm-tools/plugins/vmsvc/"
            "libdeployPkgPlugin.so"
        )
        cust64["files"][i386] = cust64["files"][p32]
        del cust64["files"][p32]
        return self._check_via_dict(
            cust64, RC_FOUND, dslist=[cust64.get("ds"), DS_NONE]
        )

    def test_vmware_envvar_no_data(self):
        """VMware: envvar transport no data"""
        self._test_ds_not_found("VMware-EnvVar-NoData")

    def test_vmware_envvar_no_virt_id(self):
        """VMware: envvar transport success if no virt id"""
        self._test_ds_found("VMware-EnvVar-NoVirtID")

    def test_vmware_envvar_activated_by_metadata(self):
        """VMware: envvar transport activated by metadata"""
        self._test_ds_found("VMware-EnvVar-Metadata")

    def test_vmware_envvar_activated_by_userdata(self):
        """VMware: envvar transport activated by userdata"""
        self._test_ds_found("VMware-EnvVar-Userdata")

    def test_vmware_envvar_activated_by_vendordata(self):
        """VMware: envvar transport activated by vendordata"""
        self._test_ds_found("VMware-EnvVar-Vendordata")

    def test_vmware_guestinfo_no_data(self):
        """VMware: guestinfo transport no data"""
        self._test_ds_not_found("VMware-GuestInfo-NoData-Rpctool")
        self._test_ds_not_found("VMware-GuestInfo-NoData-Vmtoolsd")

    def test_vmware_guestinfo_no_virt_id(self):
        """VMware: guestinfo transport fails if no virt id"""
        self._test_ds_not_found("VMware-GuestInfo-NoVirtID")

    def test_vmware_guestinfo_activated_by_metadata(self):
        """VMware: guestinfo transport activated by metadata"""
        self._test_ds_found("VMware-GuestInfo-Metadata")

    def test_vmware_guestinfo_activated_by_userdata(self):
        """VMware: guestinfo transport activated by userdata"""
        self._test_ds_found("VMware-GuestInfo-Userdata")

    def test_vmware_guestinfo_activated_by_vendordata(self):
        """VMware: guestinfo transport activated by vendordata"""
        self._test_ds_found("VMware-GuestInfo-Vendordata")


class TestAkamai(DsIdentifyBase):
    def test_found_by_sys_vendor(self):
        """ds-identify finds Akamai by system-manufacturer dmi field"""
        self._test_ds_found("Akamai")

    def test_found_by_sys_vendor_akamai(self):
        """
        ds-identify finds Akamai by system-manufacturer dmi field when set with
        name "Akamai" (expected in the future)
        """
        cfg = copy.deepcopy(VALID_CFG["Akamai"])
        cfg["mocks"][0]["RET"] = "Akamai"
        self._check_via_dict(cfg, rc=RC_FOUND)

    def test_not_found(self):
        """ds-identify does not find Akamai by system-manufacturer field"""
        cfg = copy.deepcopy(VALID_CFG["Akamai"])
        cfg["mocks"][0]["RET"] = "Other"
        self._check_via_dict(cfg, rc=RC_NOT_FOUND)


class TestBSDNoSys(DsIdentifyBase):
    """Test *BSD code paths

    FreeBSD doesn't have /sys so we use kenv(1) here.
    OpenBSD uses sysctl(8).
    Other BSD systems fallback to dmidecode(8).
    BSDs also doesn't have systemd-detect-virt(8), so we use sysctl(8) to query
    kern.vm_guest, and optionally map it"""

    def test_dmi_kenv(self):
        """Test that kenv(1) works on systems which don't have /sys

        This will be used on FreeBSD systems.
        """
        self._test_ds_found("Hetzner-kenv")

    def test_dmi_sysctl(self):
        """Test that sysctl(8) works on systems which don't have /sys

        This will be used on OpenBSD systems.
        """
        self._test_ds_found("Hetzner-sysctl")

    def test_dmi_dmidecode(self):
        """Test that dmidecode(8) works on systems which don't have /sys

        This will be used on all other BSD systems.
        """
        self._test_ds_found("Hetzner-dmidecode")


class TestIsIBMProvisioning(DsIdentifyBase):
    """Test the is_ibm_provisioning method in ds-identify."""

    inst_log = "/root/swinstall.log"
    prov_cfg = "/root/provisioningConfiguration.cfg"
    boot_ref = "/proc/1/environ"
    funcname = "is_ibm_provisioning"

    def test_no_config(self):
        """No provisioning config means not provisioning."""
        ret = self.call(files={}, func=self.funcname)
        self.assertEqual(shell_false, ret.rc)

    def test_config_only(self):
        """A provisioning config without a log means provisioning."""
        ret = self.call(files={self.prov_cfg: "key=value"}, func=self.funcname)
        self.assertEqual(shell_true, ret.rc)

    def test_config_with_old_log(self):
        """A config with a log from previous boot is not provisioning."""
        rootd = self.tmp_dir()
        data = {
            self.prov_cfg: ("key=value\nkey2=val2\n", -10),
            self.inst_log: ("log data\n", -30),
            self.boot_ref: ("PWD=/", 0),
        }
        populate_dir_with_ts(rootd, data)
        ret = self.call(rootd=rootd, func=self.funcname)
        self.assertEqual(shell_false, ret.rc)
        self.assertIn("from previous boot", ret.stderr)

    def test_config_with_new_log(self):
        """A config with a log from this boot is provisioning."""
        rootd = self.tmp_dir()
        data = {
            self.prov_cfg: ("key=value\nkey2=val2\n", -10),
            self.inst_log: ("log data\n", 30),
            self.boot_ref: ("PWD=/", 0),
        }
        populate_dir_with_ts(rootd, data)
        ret = self.call(rootd=rootd, func=self.funcname)
        self.assertEqual(shell_true, ret.rc)
        self.assertIn("from current boot", ret.stderr)


class TestOracle(DsIdentifyBase):
    def test_found_by_chassis(self):
        """Simple positive test of Oracle by chassis id."""
        self._test_ds_found("Oracle")

    def test_not_found(self):
        """Simple negative test of Oracle."""
        mycfg = copy.deepcopy(VALID_CFG["Oracle"])
        mycfg["files"][P_CHASSIS_ASSET_TAG] = "Not Oracle"
        self._check_via_dict(mycfg, rc=RC_NOT_FOUND)


class TestWSL(DsIdentifyBase):
    def test_not_found_virt(self):
        """Simple negative test for WSL due other virt."""
        self._test_ds_not_found("Not-WSL")

    def test_no_fs_mounts(self):
        """Negative test by lack of host filesystem mount points."""
        self._test_ds_not_found("WSL-no-host-mounts")

    def test_no_userprofile(self):
        """Negative test by failing to read the %USERPROFILE% environment
        variable.
        """
        data = copy.deepcopy(VALID_CFG["WSL-supported"])
        data["mocks"].append(
            {
                "name": "WSL_run_cmd",
                "ret": 0,
                "RET": "\r\n",
            },
        )
        return self._check_via_dict(data, RC_NOT_FOUND)

    def test_no_cloudinitdir_in_userprofile(self):
        """Negative test by not finding %USERPROFILE%/.cloud-init."""
        data = copy.deepcopy(VALID_CFG["WSL-supported"])
        userprofile = self.tmp_dir()
        data["mocks"].append(
            {
                "name": "WSL_profile_dir",
                "ret": 0,
                "RET": userprofile,
            },
        )
        return self._check_via_dict(data, RC_NOT_FOUND)

    def test_empty_cloudinitdir(self):
        """Negative test by lack of host filesystem mount points."""
        data = copy.deepcopy(VALID_CFG["WSL-supported"])
        userprofile = self.tmp_dir()
        data["mocks"].append(
            {
                "name": "WSL_profile_dir",
                "ret": 0,
                "RET": userprofile,
            },
        )
        cloudinitdir = os.path.join(userprofile, ".cloud-init")
        os.mkdir(cloudinitdir)
        return self._check_via_dict(data, RC_NOT_FOUND)

    def test_found_fail_due_instance_name_parsing(self):
        """WSL datasource detection fail due parsing error even though the file
        exists.
        """
        data = copy.deepcopy(VALID_CFG["WSL-supported-debian"])
        userprofile = self.tmp_dir()
        data["mocks"].append(
            {
                "name": "WSL_profile_dir",
                "ret": 0,
                "RET": userprofile,
            },
        )

        # Forcing WSL_linux2win_path to return a path we'll fail to parse
        # (missing one / in the begining of the path).
        for i, m in enumerate(data["mocks"]):
            if m["name"] == "WSL_linux2win_path":
                data["mocks"][i]["RET"] = "/wsl.localhost/cant-findme"

        cloudinitdir = os.path.join(userprofile, ".cloud-init")
        os.mkdir(cloudinitdir)
        filename = os.path.join(cloudinitdir, "cant-findme.user-data")
        Path(filename).touch()
        self._check_via_dict(data, RC_NOT_FOUND)
        Path(filename).unlink()

    def test_found_via_userdata_version_codename(self):
        """WSL datasource detected by VERSION_CODENAME when no VERSION_ID"""
        data = copy.deepcopy(VALID_CFG["WSL-supported-debian"])
        userprofile = self.tmp_dir()
        data["mocks"].append(
            {
                "name": "WSL_profile_dir",
                "ret": 0,
                "RET": userprofile,
            },
        )
        cloudinitdir = os.path.join(userprofile, ".cloud-init")
        os.mkdir(cloudinitdir)
        filename = os.path.join(cloudinitdir, "debian-trixie.user-data")
        Path(filename).touch()
        self._check_via_dict(data, RC_FOUND, dslist=[data.get("ds"), DS_NONE])
        Path(filename).unlink()

    def test_found_via_userdata(self):
        """
        WSL datasource is found on applicable userdata files in cloudinitdir.
        """
        data = copy.deepcopy(VALID_CFG["WSL-supported"])
        userprofile = self.tmp_dir()
        data["mocks"].append(
            {
                "name": "WSL_profile_dir",
                "ret": 0,
                "RET": userprofile,
            },
        )
        cloudinitdir = os.path.join(userprofile, ".cloud-init")
        os.mkdir(cloudinitdir)
        up4wcloudinitdir = os.path.join(userprofile, ".ubuntupro/.cloud-init")
        os.makedirs(up4wcloudinitdir, exist_ok=True)
        userdata_files = [
            os.path.join(
                up4wcloudinitdir, MOCK_WSL_INSTANCE_DATA["name"] + ".user-data"
            ),
            os.path.join(up4wcloudinitdir, "agent.yaml"),
            os.path.join(
                cloudinitdir, MOCK_WSL_INSTANCE_DATA["name"] + ".user-data"
            ),
            os.path.join(
                cloudinitdir,
                "%s-%s.user-data"
                % (
                    MOCK_WSL_INSTANCE_DATA["distro"],
                    MOCK_WSL_INSTANCE_DATA["version"],
                ),
            ),
            os.path.join(
                cloudinitdir,
                MOCK_WSL_INSTANCE_DATA["distro"] + "-all.user-data",
            ),
            os.path.join(cloudinitdir, "default.user-data"),
        ]

        for filename in userdata_files:
            Path(filename).touch()
            self._check_via_dict(
                data, RC_FOUND, dslist=[data.get("ds"), DS_NONE]
            )
            # Delete one by one
            Path(filename).unlink()

        # Until there is none, making the datasource no longer viable.
        return self._check_via_dict(data, RC_NOT_FOUND)


def blkid_out(disks=None):
    """Convert a list of disk dictionaries into blkid content."""
    if disks is None:
        disks = []
    lines = []
    for disk in disks:
        if not disk["DEVNAME"].startswith("/dev/"):
            disk["DEVNAME"] = "/dev/" + disk["DEVNAME"]
        # devname needs to be first.
        lines.append("%s=%s" % ("DEVNAME", disk["DEVNAME"]))
        for key in [d for d in disk if d != "DEVNAME"]:
            lines.append("%s=%s" % (key, disk[key]))
        lines.append("")
    return "\n".join(lines)


def geom_out(disks=None):
    """Convert a list of disk dictionaries into geom content.

    geom called with -a (provider) and -s (script-friendly), will produce the
    following output:

      gpt/gptboot0  N/A  vtbd1p1
         gpt/swap0  N/A  vtbd1p2
    iso9660/cidata  N/A  vtbd2
    """
    if disks is None:
        disks = []
    lines = []
    for disk in disks:
        lines.append(
            "%s/%s  N/A  %s" % (disk["TYPE"], disk["LABEL"], disk["DEVNAME"])
        )
        lines.append("")
    return "\n".join(lines)


def _print_run_output(rc, out, err, cfg, files):
    """A helper to print return of TestDsIdentify.

    _print_run_output(self.call())"""
    print(
        "\n".join(
            [
                "-- rc = %s --" % rc,
                "-- out --",
                str(out),
                "-- err --",
                str(err),
                "-- cfg --",
                atomic_helper.json_dumps(cfg),
            ]
        )
    )
    print("-- files --")
    for k, v in files.items():
        if "/_shwrap" in k:
            continue
        print(" === %s ===" % k)
        for line in v.splitlines():
            print(" " + line)


VALID_CFG = {
    "Akamai": {
        "ds": "Akamai",
        "mocks": [{"name": "dmi_decode", "ret": 0, "RET": "Linode"}],
    },
    "AliYun": {
        "ds": "AliYun",
        "files": {P_PRODUCT_NAME: "Alibaba Cloud ECS\n"},
    },
    "Azure-dmi-detection": {
        "ds": "Azure",
        "files": {
            P_CHASSIS_ASSET_TAG: "7783-7084-3265-9085-8269-3286-77\n",
        },
    },
    "Azure-seed-detection": {
        "ds": "Azure",
        "files": {
            P_CHASSIS_ASSET_TAG: "No-match\n",
            os.path.join(P_SEED_DIR, "azure", "ovf-env.xml"): "present\n",
        },
    },
    "Azure-parse-invalid": {
        "ds": "Azure",
        "files": {
            P_CHASSIS_ASSET_TAG: "7783-7084-3265-9085-8269-3286-77\n",
            "etc/cloud/cloud.cfg.d/91-azure_datasource.cfg": (
                "datasource_list:\n   - Azure"
            ),
        },
    },
    "Ec2-hvm": {
        "ds": "Ec2",
        "mocks": [{"name": "detect_virt", "RET": "kvm", "ret": 0}],
        "files": {
            P_PRODUCT_SERIAL: "ec23aef5-54be-4843-8d24-8c819f88453e\n",
            P_PRODUCT_UUID: "EC23AEF5-54BE-4843-8D24-8C819F88453E\n",
        },
    },
    "Ec2-hvm-swap-endianness": {
        "ds": "Ec2",
        "mocks": [{"name": "detect_virt", "RET": "kvm", "ret": 0}],
        "files": {
            P_PRODUCT_UUID: "AB232AEC-54BE-4843-8D24-8C819F88453E\n",
        },
    },
    "Ec2-hvm-env": {
        "ds": "Ec2",
        "mocks": [{"name": "detect_virt_env", "RET": "vm:kvm", "ret": 0}],
        "files": {
            P_PRODUCT_SERIAL: "ec23aef5-54be-4843-8d24-8c819f88453e\n",
            P_PRODUCT_UUID: "EC23AEF5-54BE-4843-8D24-8C819F88453E\n",
        },
    },
    "Ec2-xen": {
        "ds": "Ec2",
        "mocks": [MOCK_VIRT_IS_XEN],
        "files": {
            "sys/hypervisor/uuid": "ec2c6e2f-5fac-4fc7-9c82-74127ec14bbb\n"
        },
    },
    "Ec2-brightbox": {
        "ds": "Ec2",
        "files": {P_PRODUCT_SERIAL: "srv-otuxg.gb1.brightbox.com\n"},
    },
    "Ec2-brightbox-negative": {
        "ds": "Ec2",
        "files": {P_PRODUCT_SERIAL: "tricky-host.bobrightbox.com\n"},
    },
    "GCE": {
        "ds": "GCE",
        "files": {P_PRODUCT_NAME: "Google Compute Engine\n"},
        "mocks": [MOCK_VIRT_IS_KVM],
    },
    "GCE_ENV": {
        "ds": "GCE",
        "files": {P_PRODUCT_NAME: "Google Compute Engine\n"},
        "env_vars": KVM_ENV,
        "no_mocks": ["detect_virt"],
    },
    "GCE-serial": {
        "ds": "GCE",
        "files": {P_PRODUCT_SERIAL: "GoogleCloud-8f2e88f\n"},
        "mocks": [MOCK_VIRT_IS_KVM],
    },
    "LXD-kvm": {
        "ds": "LXD",
        "files": {P_BOARD_NAME: "LXD\n"},
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
    },
    "LXD-kvm-not-MAAS-1": {
        "ds": "LXD",
        "files": {
            P_BOARD_NAME: "LXD\n",
            "etc/cloud/cloud.cfg.d/92-broken-maas.cfg": (
                "datasource:\n MAAS:\n metadata_urls: [ 'blah.com' ]"
            ),
        },
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
    },
    "LXD-kvm-not-MAAS-2": {
        "ds": "LXD",
        "files": {
            P_BOARD_NAME: "LXD\n",
            "etc/cloud/cloud.cfg.d/92-broken-maas.cfg": ("#MAAS: None"),
        },
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
    },
    "LXD-kvm-not-MAAS-3": {
        "ds": "LXD",
        "files": {
            P_BOARD_NAME: "LXD\n",
            "etc/cloud/cloud.cfg.d/92-broken-maas.cfg": ("MAAS: None\n"),
        },
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
    },
    "flow_sequence-control": {
        "ds": "None",
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
        "files": {
            "etc/cloud/cloud.cfg": dedent(
                """\
                "datasource-list":  [ None    ]   \n
                """
            )
        },
    },
    # no quotes, whitespace between all chars and at the end of line
    "flow_sequence-1": {
        "ds": "None",
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
        "files": {
            "etc/cloud/cloud.cfg": dedent(
                """\
                datasource_list :  [ None    ]   \n
                """
            )
        },
    },
    # double quotes
    "flow_sequence-2": {
        "ds": "None",
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
        "files": {
            "etc/cloud/cloud.cfg": dedent(
                """\
                "datasource_list": [None]
                """
            )
        },
    },
    # single quotes
    "flow_sequence-3": {
        "ds": "None",
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
        "files": {
            "etc/cloud/cloud.cfg": dedent(
                """\
                'datasource_list': [None]
                """
            )
        },
    },
    # no newlines
    "flow_sequence-4": {
        "ds": "None",
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
        "files": {
            "etc/cloud/cloud.cfg": dedent("datasource_list:  [ None     ]")
        },
    },
    # double quoted key, single quoted list member
    "flow_sequence-5": {
        "ds": "None",
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
        "files": {
            "etc/cloud/cloud.cfg": dedent(
                "\"datasource_list\": [    'None' ]  "
            )
        },
    },
    # single quotes, whitespace before colon
    "flow_sequence-6": {
        "ds": "None",
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
        "files": {
            "etc/cloud/cloud.cfg": dedent("'datasource_list' : [    None  ]  ")
        },
    },
    "flow_sequence-7": {
        "ds": "None",
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
        "files": {
            "etc/cloud/cloud.cfg": dedent(
                '"datasource_list"     : [    None  ]  '
            )
        },
    },
    # tabs as part of whitespace between all chars
    "flow_sequence-8": {
        "ds": "None",
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
        "files": {
            "etc/cloud/cloud.cfg": dedent(
                '"datasource_list"   \t\t  : \t\t[\t   \tNone \t \t ] \t\t '
            )
        },
    },
    # no quotes, no whitespace
    "flow_sequence-9": {
        "ds": "None",
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
        "files": {"etc/cloud/cloud.cfg": dedent("datasource_list: [None]")},
    },
    "LXD-kvm-not-azure": {
        "ds": "Azure",
        "files": {
            P_BOARD_NAME: "LXD\n",
            "etc/cloud/cloud.cfg.d/92-broken-azure.cfg": (
                "datasource_list:\n - Azure"
            ),
        },
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
    },
    "LXD-kvm-qemu-kernel-gt-5.10": {  # LXD host > 5.10 kvm launch virt==qemu
        "ds": "LXD",
        "files": {P_BOARD_NAME: "LXD\n"},
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [{"name": "is_socket_file", "ret": 1}, MOCK_VIRT_IS_KVM_QEMU],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
    },
    # LXD host > 5.10 kvm launch virt==qemu
    "LXD-kvm-qemu-kernel-gt-5.10-env": {
        "ds": "LXD",
        "files": {
            P_BOARD_NAME: "LXD\n",
            # this test is systemd-specific, but may run on non-systemd systems
            # ensure that /run/systemd/ exists, such that this test will take
            # the systemd branch on those systems as well
            #
            # https://github.com/canonical/cloud-init/issues/5095
            "/run/systemd/somefile": "",
        },
        # /dev/lxd/sock does not exist and KVM virt-type
        "mocks": [
            {"name": "is_socket_file", "ret": 1},
        ],
        "env_vars": IS_KVM_QEMU_ENV,
        "no_mocks": [
            "dscheck_LXD",
            "detect_virt",
        ],  # Don't default mock dscheck_LXD
    },
    "LXD": {
        "ds": "LXD",
        # /dev/lxd/sock exists
        "mocks": [{"name": "is_socket_file", "ret": 0}],
        "no_mocks": ["dscheck_LXD"],  # Don't default mock dscheck_LXD
    },
    "NoCloud": {
        "ds": "NoCloud",
        "mocks": [
            MOCK_VIRT_IS_KVM,
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    BLKID_UEFI_UBUNTU
                    + [
                        {
                            "DEVNAME": "vdb",
                            "TYPE": "iso9660",
                            "LABEL": "cidata",
                        }
                    ]
                ),
            },
        ],
        "files": {
            "dev/vdb": "pretend iso content for cidata\n",
        },
    },
    "NoCloud-cfg": {
        "ds": "NoCloud",
        "files": {
            # Also include a datasource list of more than just
            # [NoCloud, None], because that would automatically select
            # NoCloud without checking
            "etc/cloud/cloud.cfg": dedent(
                """\
                datasource_list: [ Azure, OpenStack, NoCloud, None ]
                datasource:
                  NoCloud:
                    user-data: |
                      #cloud-config
                      hostname: footbar
                    meta-data: |
                      instance_id: cloud-image
                """
            )
        },
    },
    "NoCloud-fbsd": {
        "ds": "NoCloud",
        "mocks": [
            MOCK_VIRT_IS_KVM,
            MOCK_UNAME_IS_FREEBSD,
            {
                "name": "geom",
                "ret": 0,
                "out": geom_out(
                    [{"DEVNAME": "vtbd", "TYPE": "iso9660", "LABEL": "cidata"}]
                ),
            },
        ],
        "files": {
            "/dev/vtdb": "pretend iso content for cidata\n",
        },
    },
    "NoCloudUpper": {
        "ds": "NoCloud",
        "mocks": [
            MOCK_VIRT_IS_KVM,
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    BLKID_UEFI_UBUNTU
                    + [
                        {
                            "DEVNAME": "vdb",
                            "TYPE": "iso9660",
                            "LABEL": "CIDATA",
                        }
                    ]
                ),
            },
        ],
        "files": {
            "dev/vdb": "pretend iso content for cidata\n",
        },
    },
    "NoCloud-fatboot": {
        "ds": "NoCloud",
        "mocks": [
            MOCK_VIRT_IS_XEN,
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    BLKID_UEFI_UBUNTU
                    + [
                        {
                            "DEVNAME": "xvdb",
                            "TYPE": "vfat",
                            "SEC_TYPE": "msdos",
                            "UUID": "355a-4FC2",
                            "LABEL_FATBOOT": "cidata",
                        }
                    ]
                ),
            },
        ],
        "files": {
            "dev/vdb": "pretend iso content for cidata\n",
        },
    },
    "NoCloud-seed": {
        "ds": "NoCloud",
        "files": {
            os.path.join(P_SEED_DIR, "nocloud", "user-data"): "ud\n",
            os.path.join(P_SEED_DIR, "nocloud", "meta-data"): "md\n",
        },
    },
    "NoCloud-seed-ubuntu-core": {
        "ds": "NoCloud",
        "files": {
            os.path.join(
                "writable/system-data", P_SEED_DIR, "nocloud-net", "user-data"
            ): "ud\n",
            os.path.join(
                "writable/system-data", P_SEED_DIR, "nocloud-net", "meta-data"
            ): "md\n",
        },
    },
    "OpenStack": {
        "ds": "OpenStack",
        "files": {P_PRODUCT_NAME: "OpenStack Nova\n"},
        "mocks": [MOCK_VIRT_IS_KVM],
        "policy_dmi": POLICY_FOUND_ONLY,
        "policy_no_dmi": POLICY_FOUND_ONLY,
    },
    "OpenStack-OpenTelekom": {
        # OTC gen1 (Xen) hosts use OpenStack datasource, LP: #1756471
        "ds": "OpenStack",
        "files": {P_CHASSIS_ASSET_TAG: "OpenTelekomCloud\n"},
        "mocks": [MOCK_VIRT_IS_XEN],
    },
    "OpenStack-SAPCCloud": {
        # SAP CCloud hosts use OpenStack on VMware
        "ds": "OpenStack",
        "files": {P_CHASSIS_ASSET_TAG: "SAP CCloud VM\n"},
        "mocks": [MOCK_VIRT_IS_VMWARE],
    },
    "OpenStack-SAPCCloud-env": {
        # SAP CCloud hosts use OpenStack on VMware
        "ds": "OpenStack",
        "files": {P_CHASSIS_ASSET_TAG: "SAP CCloud VM\n"},
        "env_vars": IS_VMWARE_ENV,
        "no_mocks": ["detect_virt"],
    },
    "OpenStack-HuaweiCloud": {
        # Huawei Cloud hosts use OpenStack
        "ds": "OpenStack",
        "files": {P_CHASSIS_ASSET_TAG: "HUAWEICLOUD\n"},
        "mocks": [MOCK_VIRT_IS_KVM],
    },
    "OpenStack-AssetTag-Nova": {
        # VMware vSphere can't modify product-name, LP: #1669875
        "ds": "OpenStack",
        "files": {P_CHASSIS_ASSET_TAG: "OpenStack Nova\n"},
        "mocks": [MOCK_VIRT_IS_XEN],
    },
    "OpenStack-AssetTag-Compute": {
        # VMware vSphere can't modify product-name, LP: #1669875
        "ds": "OpenStack",
        "files": {P_CHASSIS_ASSET_TAG: "OpenStack Compute\n"},
        "mocks": [MOCK_VIRT_IS_XEN],
    },
    "OVF-seed": {
        "ds": "OVF",
        "files": {
            os.path.join(P_SEED_DIR, "ovf", "ovf-env.xml"): "present\n",
        },
    },
    "OVF": {
        "ds": "OVF",
        "mocks": [
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    [
                        {"DEVNAME": "sr0", "TYPE": "iso9660", "LABEL": ""},
                        {
                            "DEVNAME": "sr1",
                            "TYPE": "iso9660",
                            "LABEL": "ignoreme",
                        },
                        {
                            "DEVNAME": "vda1",
                            "TYPE": "vfat",
                            "PARTUUID": uuid4(),
                        },
                    ]
                ),
            },
            MOCK_VIRT_IS_VMWARE,
        ],
        "files": {
            "dev/sr0": "pretend ovf iso has " + OVF_MATCH_STRING + "\n",
            "sys/class/block/sr0/size": "2048\n",
        },
    },
    "OVF-guestinfo": {
        "ds": "OVF",
        "mocks": [
            {
                "name": "ovf_vmware_transport_guestinfo",
                "ret": 0,
                "out": '<?xml version="1.0" encoding="UTF-8"?>\n<Environment',
            },
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "ConfigDrive": {
        "ds": "ConfigDrive",
        "mocks": [
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    [
                        {
                            "DEVNAME": "vda1",
                            "TYPE": "vfat",
                            "PARTUUID": uuid4(),
                        },
                        {
                            "DEVNAME": "vda2",
                            "TYPE": "ext4",
                            "LABEL": "cloudimg-rootfs",
                            "PARTUUID": uuid4(),
                        },
                        {
                            "DEVNAME": "vdb",
                            "TYPE": "vfat",
                            "LABEL": "config-2",
                        },
                    ]
                ),
            },
        ],
    },
    "ConfigDriveUpper": {
        "ds": "ConfigDrive",
        "mocks": [
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    [
                        {
                            "DEVNAME": "vda1",
                            "TYPE": "vfat",
                            "PARTUUID": uuid4(),
                        },
                        {
                            "DEVNAME": "vda2",
                            "TYPE": "ext4",
                            "LABEL": "cloudimg-rootfs",
                            "PARTUUID": uuid4(),
                        },
                        {
                            "DEVNAME": "vdb",
                            "TYPE": "vfat",
                            "LABEL": "CONFIG-2",
                        },
                    ]
                ),
            },
        ],
    },
    "ConfigDrive-seed": {
        "ds": "ConfigDrive",
        "files": {
            os.path.join(
                P_SEED_DIR,
                "config_drive",
                "openstack",
                "latest",
                "meta_data.json",
            ): "md\n"
        },
    },
    "RbxCloud": {
        "ds": "RbxCloud",
        "mocks": [
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    [
                        {
                            "DEVNAME": "vda1",
                            "TYPE": "vfat",
                            "PARTUUID": uuid4(),
                        },
                        {
                            "DEVNAME": "vda2",
                            "TYPE": "ext4",
                            "LABEL": "cloudimg-rootfs",
                            "PARTUUID": uuid4(),
                        },
                        {"DEVNAME": "vdb", "TYPE": "vfat", "LABEL": "CLOUDMD"},
                    ]
                ),
            },
        ],
    },
    "RbxCloudLower": {
        "ds": "RbxCloud",
        "mocks": [
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    [
                        {
                            "DEVNAME": "vda1",
                            "TYPE": "vfat",
                            "PARTUUID": uuid4(),
                        },
                        {
                            "DEVNAME": "vda2",
                            "TYPE": "ext4",
                            "LABEL": "cloudimg-rootfs",
                            "PARTUUID": uuid4(),
                        },
                        {"DEVNAME": "vdb", "TYPE": "vfat", "LABEL": "cloudmd"},
                    ]
                ),
            },
        ],
    },
    "Hetzner": {
        "ds": "Hetzner",
        "files": {P_SYS_VENDOR: "Hetzner\n"},
    },
    "Hetzner-kenv": {
        "ds": "Hetzner",
        "mocks": [
            MOCK_UNAME_IS_FREEBSD,
            {"name": "get_kenv_field", "ret": 0, "RET": "Hetzner"},
        ],
    },
    "Hetzner-sysctl": {
        "ds": "Hetzner",
        "mocks": [
            MOCK_UNAME_IS_OPENBSD,
            {"name": "get_sysctl_field", "ret": 0, "RET": "Hetzner"},
        ],
    },
    "Hetzner-dmidecode": {
        "ds": "Hetzner",
        "mocks": [{"name": "dmi_decode", "ret": 0, "RET": "Hetzner"}],
    },
    "NWCS": {
        "ds": "NWCS",
        "files": {P_SYS_VENDOR: "NWCS\n"},
    },
    "NWCS-kenv": {
        "ds": "NWCS",
        "mocks": [
            MOCK_UNAME_IS_FREEBSD,
            {"name": "get_kenv_field", "ret": 0, "RET": "NWCS"},
        ],
    },
    "NWCS-dmidecode": {
        "ds": "NWCS",
        "mocks": [{"name": "dmi_decode", "ret": 0, "RET": "NWCS"}],
    },
    "IBMCloud-metadata": {
        "ds": "IBMCloud",
        "mocks": [
            MOCK_VIRT_IS_XEN,
            {"name": "is_ibm_provisioning", "ret": shell_false},
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    [
                        {
                            "DEVNAME": "xvda1",
                            "TYPE": "vfat",
                            "PARTUUID": uuid4(),
                        },
                        {
                            "DEVNAME": "xvda2",
                            "TYPE": "ext4",
                            "LABEL": "cloudimg-rootfs",
                            "PARTUUID": uuid4(),
                        },
                        {
                            "DEVNAME": "xvdb",
                            "TYPE": "vfat",
                            "LABEL": "METADATA",
                        },
                    ]
                ),
            },
        ],
    },
    "IBMCloud-config-2": {
        "ds": "IBMCloud",
        "mocks": [
            MOCK_VIRT_IS_XEN,
            {"name": "is_ibm_provisioning", "ret": shell_false},
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    [
                        {
                            "DEVNAME": "xvda1",
                            "TYPE": "ext3",
                            "PARTUUID": uuid4(),
                            "UUID": uuid4(),
                            "LABEL": "cloudimg-bootfs",
                        },
                        {
                            "DEVNAME": "xvdb",
                            "TYPE": "vfat",
                            "LABEL": "config-2",
                            "UUID": ds_ibm.IBM_CONFIG_UUID,
                        },
                        {
                            "DEVNAME": "xvda2",
                            "TYPE": "ext4",
                            "LABEL": "cloudimg-rootfs",
                            "PARTUUID": uuid4(),
                            "UUID": uuid4(),
                        },
                    ]
                ),
            },
        ],
    },
    "IBMCloud-nodisks": {
        "ds": "IBMCloud",
        "mocks": [
            MOCK_VIRT_IS_XEN,
            {"name": "is_ibm_provisioning", "ret": shell_false},
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    [
                        {
                            "DEVNAME": "xvda1",
                            "TYPE": "vfat",
                            "PARTUUID": uuid4(),
                        },
                        {
                            "DEVNAME": "xvda2",
                            "TYPE": "ext4",
                            "LABEL": "cloudimg-rootfs",
                            "PARTUUID": uuid4(),
                        },
                    ]
                ),
            },
        ],
    },
    "Oracle": {
        "ds": "Oracle",
        "files": {
            P_CHASSIS_ASSET_TAG: ds_oracle.CHASSIS_ASSET_TAG + "\n",
        },
    },
    "SmartOS-bhyve": {
        "ds": "SmartOS",
        "mocks": [
            MOCK_VIRT_IS_VM_OTHER,
            {
                "name": "blkid",
                "ret": 0,
                "out": blkid_out(
                    [
                        {
                            "DEVNAME": "vda1",
                            "TYPE": "ext4",
                            "PARTUUID": "49ec635a-01",
                        },
                        {
                            "DEVNAME": "vda2",
                            "TYPE": "swap",
                            "LABEL": "cloudimg-swap",
                            "PARTUUID": "49ec635a-02",
                        },
                    ]
                ),
            },
        ],
        "files": {P_PRODUCT_NAME: "SmartDC HVM\n"},
    },
    "SmartOS-lxbrand": {
        "ds": "SmartOS",
        "mocks": [
            MOCK_VIRT_IS_CONTAINER_OTHER,
            {
                "name": "uname",
                "ret": 0,
                "out": ("Linux BrandZ virtual linux x86_64"),
            },
            {"name": "blkid", "ret": 2, "out": ""},
        ],
        "files": {ds_smartos.METADATA_SOCKFILE: "would be a socket\n"},
    },
    "SmartOS-lxbrand-env": {
        "ds": "SmartOS",
        "mocks": [
            {
                "name": "uname",
                "ret": 0,
                "out": ("Linux BrandZ virtual linux x86_64"),
            },
            {"name": "blkid", "ret": 2, "out": ""},
        ],
        "no_mocks": ["detect_virt"],
        "env_vars": IS_CONTAINER_OTHER_ENV,
        "files": {ds_smartos.METADATA_SOCKFILE: "would be a socket\n"},
    },
    "Ec2-ZStack": {
        "ds": "Ec2",
        "files": {P_CHASSIS_ASSET_TAG: "123456.zstack.io\n"},
    },
    "Ec2-E24Cloud": {
        "ds": "Ec2",
        "files": {P_SYS_VENDOR: "e24cloud\n"},
    },
    "Ec2-E24Cloud-negative": {
        "ds": "Ec2",
        "files": {P_SYS_VENDOR: "e24cloudyday\n"},
    },
    "VMware-NoValidTransports": {
        "ds": "VMware",
        "mocks": [
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "VMware-vmware-customization": {
        "ds": "VMware",
        "mocks": [
            MOCK_VIRT_IS_VMWARE,
            {
                "name": "vmware_has_rpctool",
                "ret": 0,
                "out": "/usr/bin/vmware-rpctool",
            },
            {
                "name": "vmware_has_vmtoolsd",
                "ret": 1,
                "out": "/usr/bin/vmtoolsd",
            },
        ],
        "files": {
            # Setup vmware customization enabled
            "usr/lib/vmware-tools/plugins/vmsvc/libdeployPkgPlugin.so": "here",
            "etc/cloud/cloud.cfg": "disable_vmware_customization: false\n",
        },
    },
    "VMware-EnvVar-NoData": {
        "ds": "VMware",
        "mocks": [
            {
                "name": "vmware_has_envvar_vmx_guestinfo",
                "ret": 0,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_metadata",
                "ret": 1,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_userdata",
                "ret": 1,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_vendordata",
                "ret": 1,
            },
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "VMware-EnvVar-NoVirtID": {
        "ds": "VMware",
        "mocks": [
            {
                "name": "vmware_has_envvar_vmx_guestinfo",
                "ret": 0,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_metadata",
                "ret": 0,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_userdata",
                "ret": 1,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_vendordata",
                "ret": 1,
            },
        ],
    },
    "VMware-EnvVar-Metadata": {
        "ds": "VMware",
        "mocks": [
            {
                "name": "vmware_has_envvar_vmx_guestinfo",
                "ret": 0,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_metadata",
                "ret": 0,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_userdata",
                "ret": 1,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_vendordata",
                "ret": 1,
            },
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "VMware-EnvVar-Userdata": {
        "ds": "VMware",
        "mocks": [
            {
                "name": "vmware_has_envvar_vmx_guestinfo",
                "ret": 0,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_metadata",
                "ret": 1,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_userdata",
                "ret": 0,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_vendordata",
                "ret": 1,
            },
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "VMware-EnvVar-Vendordata": {
        "ds": "VMware",
        "mocks": [
            {
                "name": "vmware_has_envvar_vmx_guestinfo",
                "ret": 0,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_metadata",
                "ret": 1,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_userdata",
                "ret": 1,
            },
            {
                "name": "vmware_has_envvar_vmx_guestinfo_vendordata",
                "ret": 0,
            },
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "VMware-GuestInfo-NoData-Rpctool": {
        "ds": "VMware",
        "mocks": [
            {
                "name": "vmware_has_rpctool",
                "ret": 0,
                "out": "/usr/bin/vmware-rpctool",
            },
            {
                "name": "vmware_has_vmtoolsd",
                "ret": 1,
                "out": "/usr/bin/vmtoolsd",
            },
            {
                "name": "vmware_guestinfo_metadata",
                "ret": 1,
            },
            {
                "name": "vmware_guestinfo_userdata",
                "ret": 1,
            },
            {
                "name": "vmware_guestinfo_vendordata",
                "ret": 1,
            },
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "VMware-GuestInfo-NoData-Vmtoolsd": {
        "ds": "VMware",
        "policy_dmi": POLICY_FOUND_ONLY,
        "mocks": [
            {
                "name": "vmware_has_rpctool",
                "ret": 1,
                "out": "/usr/bin/vmware-rpctool",
            },
            {
                "name": "vmware_has_vmtoolsd",
                "ret": 0,
                "out": "/usr/bin/vmtoolsd",
            },
            {
                "name": "vmware_guestinfo_metadata",
                "ret": 1,
            },
            {
                "name": "vmware_guestinfo_userdata",
                "ret": 1,
            },
            {
                "name": "vmware_guestinfo_vendordata",
                "ret": 1,
            },
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "VMware-GuestInfo-NoVirtID": {
        "ds": "VMware",
        "mocks": [
            {
                "name": "vmware_has_rpctool",
                "ret": 0,
                "out": "/usr/bin/vmware-rpctool",
            },
            {
                "name": "vmware_guestinfo_metadata",
                "ret": 0,
                "out": "---",
            },
            {
                "name": "vmware_guestinfo_userdata",
                "ret": 1,
            },
            {
                "name": "vmware_guestinfo_vendordata",
                "ret": 1,
            },
        ],
    },
    "VMware-GuestInfo-Metadata": {
        "ds": "VMware",
        "mocks": [
            {
                "name": "vmware_has_rpctool",
                "ret": 1,
                "out": "/usr/bin/vmware-rpctool",
            },
            {
                "name": "vmware_has_vmtoolsd",
                "ret": 0,
                "out": "/usr/bin/vmtoolsd",
            },
            {
                "name": "vmware_guestinfo_metadata",
                "ret": 0,
                "out": "---",
            },
            {
                "name": "vmware_guestinfo_userdata",
                "ret": 1,
            },
            {
                "name": "vmware_guestinfo_vendordata",
                "ret": 1,
            },
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "VMware-GuestInfo-Userdata": {
        "ds": "VMware",
        "mocks": [
            {
                "name": "vmware_has_rpctool",
                "ret": 0,
                "out": "/usr/bin/vmware-rpctool",
            },
            {
                "name": "vmware_has_vmtoolsd",
                "ret": 1,
                "out": "/usr/bin/vmtoolsd",
            },
            {
                "name": "vmware_guestinfo_metadata",
                "ret": 1,
            },
            {
                "name": "vmware_guestinfo_userdata",
                "ret": 0,
                "out": "---",
            },
            {
                "name": "vmware_guestinfo_vendordata",
                "ret": 1,
            },
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "VMware-GuestInfo-Vendordata": {
        "ds": "VMware",
        "mocks": [
            {
                "name": "vmware_has_rpctool",
                "ret": 1,
                "out": "/usr/bin/vmware-rpctool",
            },
            {
                "name": "vmware_has_vmtoolsd",
                "ret": 0,
                "out": "/usr/bin/vmtoolsd",
            },
            {
                "name": "vmware_guestinfo_metadata",
                "ret": 1,
            },
            {
                "name": "vmware_guestinfo_userdata",
                "ret": 1,
            },
            {
                "name": "vmware_guestinfo_vendordata",
                "ret": 0,
                "out": "---",
            },
            MOCK_VIRT_IS_VMWARE,
        ],
    },
    "Ec2-Outscale": {
        "ds": "Ec2",
        "files": {
            P_PRODUCT_NAME: "3DS Outscale VM\n",
            P_SYS_VENDOR: "3DS Outscale\n",
        },
    },
    "Ec2-Outscale-negative-sysvendor": {
        "ds": "Ec2",
        "files": {
            P_PRODUCT_NAME: "3DS Outscale VM\n",
            P_SYS_VENDOR: "Not 3DS Outscale\n",
        },
    },
    "Ec2-Outscale-negative-productname": {
        "ds": "Ec2",
        "files": {
            P_PRODUCT_NAME: "Not 3DS Outscale VM\n",
            P_SYS_VENDOR: "3DS Outscale\n",
        },
    },
    "Not-WSL": {
        "ds": "WSL",
        "mocks": [
            MOCK_VIRT_IS_KVM,
        ],
    },
    "WSL-no-host-mounts": {
        "ds": "WSL",
        "mocks": [
            MOCK_VIRT_IS_WSL,
            MOCK_UNAME_IS_WSL,
        ],
        "files": {
            "proc/mounts": (
                "/dev/sdd / ext4 rw,errors=remount-ro,data=ordered 0 0\n"
                "cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec0 0\n"
                "snapfuse /snap/core22/1033 fuse.snapfuse ro,nodev,user_id=0,"
                "group_id=0,allow_other 0 0"
            ),
        },
    },
    "WSL-supported": {
        "ds": "WSL",
        "mocks": [
            MOCK_VIRT_IS_WSL,
            MOCK_UNAME_IS_WSL,
            {
                "name": "WSL_path",
                "ret": 0,
                "RET": "//wsl.localhost/%s/" % MOCK_WSL_INSTANCE_DATA["name"],
            },
        ],
        "files": {
            "proc/mounts": (
                "/dev/sdd / ext4 rw,errors=remount-ro,data=ordered 0 0\n"
                "cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec0 0\n"
                "C:\\134 /mnt/c 9p rw,dirsync,aname=drvfs;path=C:\\;uid=0;"
                "gid=0;symlinkroot=/mnt/...\n"
                "snapfuse /snap/core22/1033 fuse.snapfuse ro,nodev,user_id=0,"
                "group_id=0,allow_other 0 0"
            ),
            "etc/os-release": MOCK_WSL_INSTANCE_DATA["os_release"],
        },
    },
    "WSL-supported-debian": {
        "ds": "WSL",
        "mocks": [
            MOCK_VIRT_IS_WSL,
            MOCK_UNAME_IS_WSL,
            {
                "name": "WSL_path",
                "ret": 0,
                "RET": "//wsl.localhost/%s/" % MOCK_WSL_INSTANCE_DATA["name"],
            },
        ],
        "files": {
            "proc/mounts": (
                "/dev/sdd / ext4 rw,errors=remount-ro,data=ordered 0 0\n"
                "cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec0 0\n"
                "C:\\134 /mnt/c 9p rw,dirsync,aname=drvfs;path=C:\\;uid=0;"
                "gid=0;symlinkroot=/mnt/...\n"
                "snapfuse /snap/core22/1033 fuse.snapfuse ro,nodev,user_id=0,"
                "group_id=0,allow_other 0 0"
            ),
            "etc/os-release": MOCK_WSL_INSTANCE_DATA[
                "os_release_no_version_id"
            ],
        },
    },
}
