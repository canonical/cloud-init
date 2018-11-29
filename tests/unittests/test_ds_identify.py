# This file is part of cloud-init. See LICENSE file for license information.

from collections import namedtuple
import copy
import os
from uuid import uuid4

from cloudinit import safeyaml
from cloudinit import util
from cloudinit.tests.helpers import (
    CiTestCase, dir2dict, populate_dir, populate_dir_with_ts)

from cloudinit.sources import DataSourceIBMCloud as ds_ibm
from cloudinit.sources import DataSourceSmartOS as ds_smartos
from cloudinit.sources import DataSourceOracle as ds_oracle

UNAME_MYSYS = ("Linux bart 4.4.0-62-generic #83-Ubuntu "
               "SMP Wed Jan 18 14:10:15 UTC 2017 x86_64 GNU/Linux")
UNAME_PPC64EL = ("Linux diamond 4.4.0-83-generic #106-Ubuntu SMP "
                 "Mon Jun 26 17:53:54 UTC 2017 "
                 "ppc64le ppc64le ppc64le GNU/Linux")

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
    {'DEVNAME': 'vda1', 'TYPE': 'ext4', 'PARTUUID': uuid4(), 'UUID': uuid4()},
    {'DEVNAME': 'vda14', 'PARTUUID': uuid4()},
    {'DEVNAME': 'vda15', 'TYPE': 'vfat', 'LABEL': 'UEFI', 'PARTUUID': uuid4(),
     'UUID': '5F55-129B'}]


POLICY_FOUND_ONLY = "search,found=all,maybe=none,notfound=disabled"
POLICY_FOUND_OR_MAYBE = "search,found=all,maybe=all,notfound=disabled"
DI_DEFAULT_POLICY = "search,found=all,maybe=all,notfound=disabled"
DI_DEFAULT_POLICY_NO_DMI = "search,found=all,maybe=all,notfound=enabled"
DI_EC2_STRICT_ID_DEFAULT = "true"
OVF_MATCH_STRING = 'http://schemas.dmtf.org/ovf/environment/1'

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
DS_NONE = 'None'

P_CHASSIS_ASSET_TAG = "sys/class/dmi/id/chassis_asset_tag"
P_PRODUCT_NAME = "sys/class/dmi/id/product_name"
P_PRODUCT_SERIAL = "sys/class/dmi/id/product_serial"
P_PRODUCT_UUID = "sys/class/dmi/id/product_uuid"
P_SYS_VENDOR = "sys/class/dmi/id/sys_vendor"
P_SEED_DIR = "var/lib/cloud/seed"
P_DSID_CFG = "etc/cloud/ds-identify.cfg"

IBM_CONFIG_UUID = "9796-932E"

MOCK_VIRT_IS_CONTAINER_OTHER = {'name': 'detect_virt',
                                'RET': 'container-other', 'ret': 0}
MOCK_VIRT_IS_KVM = {'name': 'detect_virt', 'RET': 'kvm', 'ret': 0}
MOCK_VIRT_IS_VMWARE = {'name': 'detect_virt', 'RET': 'vmware', 'ret': 0}
# currenty' SmartOS hypervisor "bhyve" is unknown by systemd-detect-virt.
MOCK_VIRT_IS_VM_OTHER = {'name': 'detect_virt', 'RET': 'vm-other', 'ret': 0}
MOCK_VIRT_IS_XEN = {'name': 'detect_virt', 'RET': 'xen', 'ret': 0}
MOCK_UNAME_IS_PPC64 = {'name': 'uname', 'out': UNAME_PPC64EL, 'ret': 0}

shell_true = 0
shell_false = 1

CallReturn = namedtuple('CallReturn',
                        ['rc', 'stdout', 'stderr', 'cfg', 'files'])


class DsIdentifyBase(CiTestCase):
    dsid_path = os.path.realpath('tools/ds-identify')
    allowed_subp = ['sh']

    def call(self, rootd=None, mocks=None, func="main", args=None, files=None,
             policy_dmi=DI_DEFAULT_POLICY,
             policy_no_dmi=DI_DEFAULT_POLICY_NO_DMI,
             ec2_strict_id=DI_EC2_STRICT_ID_DEFAULT):
        if args is None:
            args = []
        if mocks is None:
            mocks = []

        if files is None:
            files = {}

        if rootd is None:
            rootd = self.tmp_dir()

        unset = '_unset'
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
            ""
        ]

        def write_mock(data):
            ddata = {'out': None, 'err': None, 'ret': 0, 'RET': None}
            ddata.update(data)
            for k in ddata:
                if ddata[k] is None:
                    ddata[k] = unset
            return SHELL_MOCK_TMPL % ddata

        mocklines = []
        defaults = [
            {'name': 'detect_virt', 'RET': 'none', 'ret': 1},
            {'name': 'uname', 'out': UNAME_MYSYS},
            {'name': 'blkid', 'out': BLKID_EFI_ROOT},
        ]

        written = [d['name'] for d in mocks]
        for data in mocks:
            mocklines.append(write_mock(data))
        for d in defaults:
            if d['name'] not in written:
                mocklines.append(write_mock(d))

        endlines = [
            func + ' ' + ' '.join(['"%s"' % s for s in args])
        ]

        with open(wrap, "w") as fp:
            fp.write('\n'.join(head + mocklines + endlines) + "\n")

        rc = 0
        try:
            out, err = util.subp(['sh', '-c', '. %s' % wrap], capture=True)
        except util.ProcessExecutionError as e:
            rc = e.exit_code
            out = e.stdout
            err = e.stderr

        cfg = None
        cfg_out = os.path.join(rootd, 'run/cloud-init/cloud.cfg')
        if os.path.exists(cfg_out):
            contents = util.load_file(cfg_out)
            try:
                cfg = safeyaml.load(contents)
            except Exception as e:
                cfg = {"_INVALID_YAML": contents,
                       "_EXCEPTION": str(e)}

        return CallReturn(rc, out, err, cfg, dir2dict(rootd))

    def _call_via_dict(self, data, rootd=None, **kwargs):
        # return output of self.call with a dict input like VALID_CFG[item]
        xwargs = {'rootd': rootd}
        passthrough = ('mocks', 'func', 'args', 'policy_dmi',
                       'policy_no_dmi', 'files')
        for k in passthrough:
            if k in data:
                xwargs[k] = data[k]
            if k in kwargs:
                xwargs[k] = kwargs[k]

        return self.call(**xwargs)

    def _test_ds_found(self, name):
        data = copy.deepcopy(VALID_CFG[name])
        return self._check_via_dict(
            data, RC_FOUND, dslist=[data.get('ds'), DS_NONE])

    def _check_via_dict(self, data, rc, dslist=None, **kwargs):
        ret = self._call_via_dict(data, **kwargs)
        good = False
        try:
            self.assertEqual(rc, ret.rc)
            if dslist is not None:
                self.assertEqual(dslist, ret.cfg['datasource_list'])
            good = True
        finally:
            if not good:
                _print_run_output(ret.rc, ret.stdout, ret.stderr, ret.cfg,
                                  ret.files)
        return ret


class TestDsIdentify(DsIdentifyBase):
    def test_wb_print_variables(self):
        """_print_info reports an array of discovered variables to stderr."""
        data = VALID_CFG['Azure-dmi-detection']
        _, _, err, _, _ = self._call_via_dict(data)
        expected_vars = [
            'DMI_PRODUCT_NAME', 'DMI_SYS_VENDOR', 'DMI_PRODUCT_SERIAL',
            'DMI_PRODUCT_UUID', 'PID_1_PRODUCT_NAME', 'DMI_CHASSIS_ASSET_TAG',
            'FS_LABELS', 'KERNEL_CMDLINE', 'VIRT', 'UNAME_KERNEL_NAME',
            'UNAME_KERNEL_RELEASE', 'UNAME_KERNEL_VERSION', 'UNAME_MACHINE',
            'UNAME_NODENAME', 'UNAME_OPERATING_SYSTEM', 'DSNAME', 'DSLIST',
            'MODE', 'ON_FOUND', 'ON_MAYBE', 'ON_NOTFOUND']
        for var in expected_vars:
            self.assertIn('{0}='.format(var), err)

    def test_azure_dmi_detection_from_chassis_asset_tag(self):
        """Azure datasource is detected from DMI chassis-asset-tag"""
        self._test_ds_found('Azure-dmi-detection')

    def test_azure_seed_file_detection(self):
        """Azure datasource is detected due to presence of a seed file.

        The seed file tested  is /var/lib/cloud/seed/azure/ovf-env.xml."""
        self._test_ds_found('Azure-seed-detection')

    def test_aws_ec2_hvm(self):
        """EC2: hvm instances use dmi serial and uuid starting with 'ec2'."""
        self._test_ds_found('Ec2-hvm')

    def test_aws_ec2_xen(self):
        """EC2: sys/hypervisor/uuid starts with ec2."""
        self._test_ds_found('Ec2-xen')

    def test_brightbox_is_ec2(self):
        """EC2: product_serial ends with 'brightbox.com'"""
        self._test_ds_found('Ec2-brightbox')

    def test_gce_by_product_name(self):
        """GCE identifies itself with product_name."""
        self._test_ds_found('GCE')

    def test_gce_by_serial(self):
        """Older gce compute instances must be identified by serial."""
        self._test_ds_found('GCE-serial')

    def test_config_drive(self):
        """ConfigDrive datasource has a disk with LABEL=config-2."""
        self._test_ds_found('ConfigDrive')

    def test_config_drive_upper(self):
        """ConfigDrive datasource has a disk with LABEL=CONFIG-2."""
        self._test_ds_found('ConfigDriveUpper')
        return

    def test_config_drive_seed(self):
        """Config Drive seed directory."""
        self._test_ds_found('ConfigDrive-seed')

    def test_config_drive_interacts_with_ibmcloud_config_disk(self):
        """Verify ConfigDrive interaction with IBMCloud.

        If ConfigDrive is enabled and not IBMCloud, then ConfigDrive
        should claim the ibmcloud 'config-2' disk.
        If IBMCloud is enabled, then ConfigDrive should skip."""
        data = copy.deepcopy(VALID_CFG['IBMCloud-config-2'])
        files = data.get('files', {})
        if not files:
            data['files'] = files
        cfgpath = 'etc/cloud/cloud.cfg.d/99_networklayer_common.cfg'

        # with list including IBMCloud, config drive should be not found.
        files[cfgpath] = 'datasource_list: [ ConfigDrive, IBMCloud ]\n'
        ret = self._check_via_dict(data, shell_true)
        self.assertEqual(
            ret.cfg.get('datasource_list'), ['IBMCloud', 'None'])

        # But if IBMCloud is not enabled, config drive should claim this.
        files[cfgpath] = 'datasource_list: [ ConfigDrive, NoCloud ]\n'
        ret = self._check_via_dict(data, shell_true)
        self.assertEqual(
            ret.cfg.get('datasource_list'), ['ConfigDrive', 'None'])

    def test_ibmcloud_template_userdata_in_provisioning(self):
        """Template provisioned with user-data during provisioning stage.

        Template provisioning with user-data has METADATA disk,
        datasource should return not found."""
        data = copy.deepcopy(VALID_CFG['IBMCloud-metadata'])
        # change the 'is_ibm_provisioning' mock to return 1 (false)
        isprov_m = [m for m in data['mocks']
                    if m["name"] == "is_ibm_provisioning"][0]
        isprov_m['ret'] = shell_true
        return self._check_via_dict(data, RC_NOT_FOUND)

    def test_ibmcloud_template_userdata(self):
        """Template provisioned with user-data first boot.

        Template provisioning with user-data has METADATA disk.
        datasource should return found."""
        self._test_ds_found('IBMCloud-metadata')

    def test_ibmcloud_template_no_userdata_in_provisioning(self):
        """Template provisioned with no user-data during provisioning.

        no disks attached.  Datasource should return not found."""
        data = copy.deepcopy(VALID_CFG['IBMCloud-nodisks'])
        data['mocks'].append(
            {'name': 'is_ibm_provisioning', 'ret': shell_true})
        return self._check_via_dict(data, RC_NOT_FOUND)

    def test_ibmcloud_template_no_userdata(self):
        """Template provisioned with no user-data first boot.

        no disks attached.  Datasource should return found."""
        self._check_via_dict(VALID_CFG['IBMCloud-nodisks'], RC_NOT_FOUND)

    def test_ibmcloud_os_code(self):
        """Launched by os code always has config-2 disk."""
        self._test_ds_found('IBMCloud-config-2')

    def test_ibmcloud_os_code_different_uuid(self):
        """IBM cloud config-2 disks must be explicit match on UUID.

        If the UUID is not 9796-932E then we actually expect ConfigDrive."""
        data = copy.deepcopy(VALID_CFG['IBMCloud-config-2'])
        offset = None
        for m, d in enumerate(data['mocks']):
            if d.get('name') == "blkid":
                offset = m
                break
        if not offset:
            raise ValueError("Expected to find 'blkid' mock, but did not.")
        data['mocks'][offset]['out'] = d['out'].replace(ds_ibm.IBM_CONFIG_UUID,
                                                        "DEAD-BEEF")
        self._check_via_dict(
            data, rc=RC_FOUND, dslist=['ConfigDrive', DS_NONE])

    def test_ibmcloud_with_nocloud_seed(self):
        """NoCloud seed should be preferred over IBMCloud.

        A nocloud seed should be preferred over IBMCloud even if enabled.
        Ubuntu 16.04 images have <vlc>/seed/nocloud-net. LP: #1766401."""
        data = copy.deepcopy(VALID_CFG['IBMCloud-config-2'])
        files = data.get('files', {})
        if not files:
            data['files'] = files
        files.update(VALID_CFG['NoCloud-seed']['files'])
        ret = self._check_via_dict(data, shell_true)
        self.assertEqual(
            ['NoCloud', 'IBMCloud', 'None'],
            ret.cfg.get('datasource_list'))

    def test_ibmcloud_with_configdrive_seed(self):
        """ConfigDrive seed should be preferred over IBMCloud.

        A ConfigDrive seed should be preferred over IBMCloud even if enabled.
        Ubuntu 16.04 images have a fstab entry that mounts the
        METADATA disk into <vlc>/seed/config_drive. LP: ##1766401."""
        data = copy.deepcopy(VALID_CFG['IBMCloud-config-2'])
        files = data.get('files', {})
        if not files:
            data['files'] = files
        files.update(VALID_CFG['ConfigDrive-seed']['files'])
        ret = self._check_via_dict(data, shell_true)
        self.assertEqual(
            ['ConfigDrive', 'IBMCloud', 'None'],
            ret.cfg.get('datasource_list'))

    def test_policy_disabled(self):
        """A Builtin policy of 'disabled' should return not found.

        Even though a search would find something, the builtin policy of
        disabled should cause the return of not found."""
        mydata = copy.deepcopy(VALID_CFG['Ec2-hvm'])
        self._check_via_dict(mydata, rc=RC_NOT_FOUND, policy_dmi="disabled")

    def test_policy_config_disable_overrides_builtin(self):
        """explicit policy: disabled in config file should cause not found."""
        mydata = copy.deepcopy(VALID_CFG['Ec2-hvm'])
        mydata['files'][P_DSID_CFG] = '\n'.join(['policy: disabled', ''])
        self._check_via_dict(mydata, rc=RC_NOT_FOUND)

    def test_single_entry_defines_datasource(self):
        """If config has a single entry in datasource_list, that is used.

        Test the valid Ec2-hvm, but provide a config file that specifies
        a single entry in datasource_list.  The configured value should
        be used."""
        mydata = copy.deepcopy(VALID_CFG['Ec2-hvm'])
        cfgpath = 'etc/cloud/cloud.cfg.d/myds.cfg'
        mydata['files'][cfgpath] = 'datasource_list: ["NoCloud"]\n'
        self._check_via_dict(mydata, rc=RC_FOUND, dslist=['NoCloud', DS_NONE])

    def test_configured_list_with_none(self):
        """When datasource_list already contains None, None is not added.

        The explicitly configured datasource_list has 'None' in it.  That
        should not have None automatically added."""
        mydata = copy.deepcopy(VALID_CFG['GCE'])
        cfgpath = 'etc/cloud/cloud.cfg.d/myds.cfg'
        mydata['files'][cfgpath] = 'datasource_list: ["Ec2", "None"]\n'
        self._check_via_dict(mydata, rc=RC_FOUND, dslist=['Ec2', DS_NONE])

    def test_aliyun_identified(self):
        """Test that Aliyun cloud is identified by product id."""
        self._test_ds_found('AliYun')

    def test_aliyun_over_ec2(self):
        """Even if all other factors identified Ec2, AliYun should be used."""
        mydata = copy.deepcopy(VALID_CFG['Ec2-xen'])
        self._test_ds_found('AliYun')
        prod_name = VALID_CFG['AliYun']['files'][P_PRODUCT_NAME]
        mydata['files'][P_PRODUCT_NAME] = prod_name
        policy = "search,found=first,maybe=none,notfound=disabled"
        self._check_via_dict(mydata, rc=RC_FOUND, dslist=['AliYun', DS_NONE],
                             policy_dmi=policy)

    def test_default_openstack_intel_is_found(self):
        """On Intel, openstack must be identified."""
        self._test_ds_found('OpenStack')

    def test_openstack_open_telekom_cloud(self):
        """Open Telecom identification."""
        self._test_ds_found('OpenStack-OpenTelekom')

    def test_openstack_on_non_intel_is_maybe(self):
        """On non-Intel, openstack without dmi info is maybe.

        nova does not identify itself on platforms other than intel.
           https://bugs.launchpad.net/cloud-init/+bugs?field.tag=dsid-nova"""

        data = VALID_CFG['OpenStack'].copy()
        del data['files'][P_PRODUCT_NAME]
        data.update({'policy_dmi': POLICY_FOUND_OR_MAYBE,
                     'policy_no_dmi': POLICY_FOUND_OR_MAYBE})

        # this should show not found as default uname in tests is intel.
        # and intel openstack requires positive identification.
        self._check_via_dict(data, RC_NOT_FOUND, dslist=None)

        # updating the uname to ppc64 though should get a maybe.
        data.update({'mocks': [MOCK_VIRT_IS_KVM, MOCK_UNAME_IS_PPC64]})
        (_, _, err, _, _) = self._check_via_dict(
            data, RC_FOUND, dslist=['OpenStack', 'None'])
        self.assertIn("check for 'OpenStack' returned maybe", err)

    def test_default_ovf_is_found(self):
        """OVF is identified found when ovf/ovf-env.xml seed file exists."""
        self._test_ds_found('OVF-seed')

    def test_default_ovf_with_detect_virt_none_not_found(self):
        """OVF identifies not found when detect_virt returns "none"."""
        self._check_via_dict(
            {'ds': 'OVF'}, rc=RC_NOT_FOUND, policy_dmi="disabled")

    def test_default_ovf_returns_not_found_on_azure(self):
        """OVF datasource won't be found as false positive on Azure."""
        ovfonazure = copy.deepcopy(VALID_CFG['OVF'])
        # Set azure asset tag to assert OVF content not found
        ovfonazure['files'][P_CHASSIS_ASSET_TAG] = (
            '7783-7084-3265-9085-8269-3286-77\n')
        self._check_via_dict(
            ovfonazure, RC_FOUND, dslist=['Azure', DS_NONE])

    def test_ovf_on_vmware_iso_found_by_cdrom_with_ovf_schema_match(self):
        """OVF is identified when iso9660 cdrom path contains ovf schema."""
        self._test_ds_found('OVF')

    def test_ovf_on_vmware_iso_found_when_vmware_customization(self):
        """OVF is identified when vmware customization is enabled."""
        self._test_ds_found('OVF-vmware-customization')

    def test_ovf_on_vmware_iso_found_open_vm_tools_64(self):
        """OVF is identified when open-vm-tools installed in /usr/lib64."""
        cust64 = copy.deepcopy(VALID_CFG['OVF-vmware-customization'])
        p32 = 'usr/lib/vmware-tools/plugins/vmsvc/libdeployPkgPlugin.so'
        open64 = 'usr/lib64/open-vm-tools/plugins/vmsvc/libdeployPkgPlugin.so'
        cust64['files'][open64] = cust64['files'][p32]
        del cust64['files'][p32]
        return self._check_via_dict(
            cust64, RC_FOUND, dslist=[cust64.get('ds'), DS_NONE])

    def test_ovf_on_vmware_iso_found_by_cdrom_with_matching_fs_label(self):
        """OVF is identified by well-known iso9660 labels."""
        ovf_cdrom_by_label = copy.deepcopy(VALID_CFG['OVF'])
        # Unset matching cdrom ovf schema content
        ovf_cdrom_by_label['files']['dev/sr0'] = 'No content match'
        self._check_via_dict(
            ovf_cdrom_by_label, rc=RC_NOT_FOUND, policy_dmi="disabled")

        # Add recognized labels
        valid_ovf_labels = ['ovf-transport', 'OVF-TRANSPORT',
                            "OVFENV", "ovfenv", "OVF ENV", "ovf env"]
        for valid_ovf_label in valid_ovf_labels:
            ovf_cdrom_by_label['mocks'][0]['out'] = blkid_out([
                {'DEVNAME': 'sda1', 'TYPE': 'ext4', 'LABEL': 'rootfs'},
                {'DEVNAME': 'sr0', 'TYPE': 'iso9660',
                 'LABEL': valid_ovf_label},
                {'DEVNAME': 'vda1', 'TYPE': 'ntfs', 'LABEL': 'data'}])
            self._check_via_dict(
                ovf_cdrom_by_label, rc=RC_FOUND, dslist=['OVF', DS_NONE])

    def test_default_nocloud_as_vdb_iso9660(self):
        """NoCloud is found with iso9660 filesystem on non-cdrom disk."""
        self._test_ds_found('NoCloud')

    def test_nocloud_seed(self):
        """Nocloud seed directory."""
        self._test_ds_found('NoCloud-seed')

    def test_nocloud_seed_ubuntu_core_writable(self):
        """Nocloud seed directory ubuntu core writable"""
        self._test_ds_found('NoCloud-seed-ubuntu-core')

    def test_hetzner_found(self):
        """Hetzner cloud is identified in sys_vendor."""
        self._test_ds_found('Hetzner')

    def test_smartos_bhyve(self):
        """SmartOS cloud identified by SmartDC in dmi."""
        self._test_ds_found('SmartOS-bhyve')

    def test_smartos_lxbrand(self):
        """SmartOS cloud identified on lxbrand container."""
        self._test_ds_found('SmartOS-lxbrand')

    def test_smartos_lxbrand_requires_socket(self):
        """SmartOS cloud should not be identified if no socket file."""
        mycfg = copy.deepcopy(VALID_CFG['SmartOS-lxbrand'])
        del mycfg['files'][ds_smartos.METADATA_SOCKFILE]
        self._check_via_dict(mycfg, rc=RC_NOT_FOUND, policy_dmi="disabled")

    def test_path_env_gets_set_from_main(self):
        """PATH environment should always have some tokens when main is run.

        We explicitly call main as we want to ensure it updates PATH."""
        cust = copy.deepcopy(VALID_CFG['NoCloud'])
        rootd = self.tmp_dir()
        mpp = 'main-printpath'
        pre = "MYPATH="
        cust['files'][mpp] = (
            'PATH="/mycust/path"; main; r=$?; echo ' + pre + '$PATH; exit $r;')
        ret = self._check_via_dict(
            cust, RC_FOUND,
            func=".", args=[os.path.join(rootd, mpp)], rootd=rootd)
        line = [l for l in ret.stdout.splitlines() if l.startswith(pre)][0]
        toks = line.replace(pre, "").split(":")
        expected = ["/sbin", "/bin", "/usr/sbin", "/usr/bin", "/mycust/path"]
        self.assertEqual(expected, [p for p in expected if p in toks],
                         "path did not have expected tokens")


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
        data = {self.prov_cfg: ("key=value\nkey2=val2\n", -10),
                self.inst_log: ("log data\n", -30),
                self.boot_ref: ("PWD=/", 0)}
        populate_dir_with_ts(rootd, data)
        ret = self.call(rootd=rootd, func=self.funcname)
        self.assertEqual(shell_false, ret.rc)
        self.assertIn("from previous boot", ret.stderr)

    def test_config_with_new_log(self):
        """A config with a log from this boot is provisioning."""
        rootd = self.tmp_dir()
        data = {self.prov_cfg: ("key=value\nkey2=val2\n", -10),
                self.inst_log: ("log data\n", 30),
                self.boot_ref: ("PWD=/", 0)}
        populate_dir_with_ts(rootd, data)
        ret = self.call(rootd=rootd, func=self.funcname)
        self.assertEqual(shell_true, ret.rc)
        self.assertIn("from current boot", ret.stderr)


class TestOracle(DsIdentifyBase):
    def test_found_by_chassis(self):
        """Simple positive test of Oracle by chassis id."""
        self._test_ds_found('Oracle')

    def test_not_found(self):
        """Simple negative test of Oracle."""
        mycfg = copy.deepcopy(VALID_CFG['Oracle'])
        mycfg['files'][P_CHASSIS_ASSET_TAG] = "Not Oracle"
        self._check_via_dict(mycfg, rc=RC_NOT_FOUND)


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
    return '\n'.join(lines)


def _print_run_output(rc, out, err, cfg, files):
    """A helper to print return of TestDsIdentify.

       _print_run_output(self.call())"""
    print('\n'.join([
        '-- rc = %s --' % rc,
        '-- out --', str(out),
        '-- err --', str(err),
        '-- cfg --', util.json_dumps(cfg)]))
    print('-- files --')
    for k, v in files.items():
        if "/_shwrap" in k:
            continue
        print(' === %s ===' % k)
        for line in v.splitlines():
            print(" " + line)


VALID_CFG = {
    'AliYun': {
        'ds': 'AliYun',
        'files': {P_PRODUCT_NAME: 'Alibaba Cloud ECS\n'},
    },
    'Azure-dmi-detection': {
        'ds': 'Azure',
        'files': {
            P_CHASSIS_ASSET_TAG: '7783-7084-3265-9085-8269-3286-77\n',
        }
    },
    'Azure-seed-detection': {
        'ds': 'Azure',
        'files': {
            P_CHASSIS_ASSET_TAG: 'No-match\n',
            os.path.join(P_SEED_DIR, 'azure', 'ovf-env.xml'): 'present\n',
        }
    },
    'Ec2-hvm': {
        'ds': 'Ec2',
        'mocks': [{'name': 'detect_virt', 'RET': 'kvm', 'ret': 0}],
        'files': {
            P_PRODUCT_SERIAL: 'ec23aef5-54be-4843-8d24-8c819f88453e\n',
            P_PRODUCT_UUID: 'EC23AEF5-54BE-4843-8D24-8C819F88453E\n',
        }
    },
    'Ec2-xen': {
        'ds': 'Ec2',
        'mocks': [MOCK_VIRT_IS_XEN],
        'files': {
            'sys/hypervisor/uuid': 'ec2c6e2f-5fac-4fc7-9c82-74127ec14bbb\n'
        },
    },
    'Ec2-brightbox': {
        'ds': 'Ec2',
        'files': {P_PRODUCT_SERIAL: 'facc6e2f.brightbox.com\n'},
    },
    'GCE': {
        'ds': 'GCE',
        'files': {P_PRODUCT_NAME: 'Google Compute Engine\n'},
        'mocks': [MOCK_VIRT_IS_KVM],
    },
    'GCE-serial': {
        'ds': 'GCE',
        'files': {P_PRODUCT_SERIAL: 'GoogleCloud-8f2e88f\n'},
        'mocks': [MOCK_VIRT_IS_KVM],
    },
    'NoCloud': {
        'ds': 'NoCloud',
        'mocks': [
            MOCK_VIRT_IS_KVM,
            {'name': 'blkid', 'ret': 0,
             'out': blkid_out(
                 BLKID_UEFI_UBUNTU +
                 [{'DEVNAME': 'vdb', 'TYPE': 'iso9660', 'LABEL': 'cidata'}])},
        ],
        'files': {
            'dev/vdb': 'pretend iso content for cidata\n',
        }
    },
    'NoCloud-seed': {
        'ds': 'NoCloud',
        'files': {
            os.path.join(P_SEED_DIR, 'nocloud', 'user-data'): 'ud\n',
            os.path.join(P_SEED_DIR, 'nocloud', 'meta-data'): 'md\n',
        }
    },
    'NoCloud-seed-ubuntu-core': {
        'ds': 'NoCloud',
        'files': {
            os.path.join('writable/system-data', P_SEED_DIR,
                         'nocloud-net', 'user-data'): 'ud\n',
            os.path.join('writable/system-data', P_SEED_DIR,
                         'nocloud-net', 'meta-data'): 'md\n',
        }
    },
    'OpenStack': {
        'ds': 'OpenStack',
        'files': {P_PRODUCT_NAME: 'OpenStack Nova\n'},
        'mocks': [MOCK_VIRT_IS_KVM],
        'policy_dmi': POLICY_FOUND_ONLY,
        'policy_no_dmi': POLICY_FOUND_ONLY,
    },
    'OpenStack-OpenTelekom': {
        # OTC gen1 (Xen) hosts use OpenStack datasource, LP: #1756471
        'ds': 'OpenStack',
        'files': {P_CHASSIS_ASSET_TAG: 'OpenTelekomCloud\n'},
        'mocks': [MOCK_VIRT_IS_XEN],
    },
    'OVF-seed': {
        'ds': 'OVF',
        'files': {
            os.path.join(P_SEED_DIR, 'ovf', 'ovf-env.xml'): 'present\n',
        }
    },
    'OVF-vmware-customization': {
        'ds': 'OVF',
        'mocks': [
            # Include a mockes iso9660 potential, even though content not ovf
            {'name': 'blkid', 'ret': 0,
             'out': blkid_out(
                 [{'DEVNAME': 'sr0', 'TYPE': 'iso9660', 'LABEL': ''}])
             },
            MOCK_VIRT_IS_VMWARE,
        ],
        'files': {
            'dev/sr0': 'no match',
            # Setup vmware customization enabled
            'usr/lib/vmware-tools/plugins/vmsvc/libdeployPkgPlugin.so': 'here',
            'etc/cloud/cloud.cfg': 'disable_vmware_customization: false\n',
        }
    },
    'OVF': {
        'ds': 'OVF',
        'mocks': [
            {'name': 'blkid', 'ret': 0,
             'out': blkid_out(
                 [{'DEVNAME': 'sr0', 'TYPE': 'iso9660', 'LABEL': ''},
                  {'DEVNAME': 'sr1', 'TYPE': 'iso9660', 'LABEL': 'ignoreme'},
                  {'DEVNAME': 'vda1', 'TYPE': 'vfat', 'PARTUUID': uuid4()}]),
             },
            MOCK_VIRT_IS_VMWARE,
        ],
        'files': {
            'dev/sr0': 'pretend ovf iso has ' + OVF_MATCH_STRING + '\n',
        }
    },
    'ConfigDrive': {
        'ds': 'ConfigDrive',
        'mocks': [
            {'name': 'blkid', 'ret': 0,
             'out': blkid_out(
                 [{'DEVNAME': 'vda1', 'TYPE': 'vfat', 'PARTUUID': uuid4()},
                  {'DEVNAME': 'vda2', 'TYPE': 'ext4',
                   'LABEL': 'cloudimg-rootfs', 'PARTUUID': uuid4()},
                  {'DEVNAME': 'vdb', 'TYPE': 'vfat', 'LABEL': 'config-2'}])
             },
        ],
    },
    'ConfigDriveUpper': {
        'ds': 'ConfigDrive',
        'mocks': [
            {'name': 'blkid', 'ret': 0,
             'out': blkid_out(
                 [{'DEVNAME': 'vda1', 'TYPE': 'vfat', 'PARTUUID': uuid4()},
                  {'DEVNAME': 'vda2', 'TYPE': 'ext4',
                   'LABEL': 'cloudimg-rootfs', 'PARTUUID': uuid4()},
                  {'DEVNAME': 'vdb', 'TYPE': 'vfat', 'LABEL': 'CONFIG-2'}])
             },
        ],
    },
    'ConfigDrive-seed': {
        'ds': 'ConfigDrive',
        'files': {
            os.path.join(P_SEED_DIR, 'config_drive', 'openstack',
                         'latest', 'meta_data.json'): 'md\n'},
    },
    'Hetzner': {
        'ds': 'Hetzner',
        'files': {P_SYS_VENDOR: 'Hetzner\n'},
    },
    'IBMCloud-metadata': {
        'ds': 'IBMCloud',
        'mocks': [
            MOCK_VIRT_IS_XEN,
            {'name': 'is_ibm_provisioning', 'ret': shell_false},
            {'name': 'blkid', 'ret': 0,
             'out': blkid_out(
                 [{'DEVNAME': 'xvda1', 'TYPE': 'vfat', 'PARTUUID': uuid4()},
                  {'DEVNAME': 'xvda2', 'TYPE': 'ext4',
                   'LABEL': 'cloudimg-rootfs', 'PARTUUID': uuid4()},
                  {'DEVNAME': 'xvdb', 'TYPE': 'vfat', 'LABEL': 'METADATA'}]),
             },
        ],
    },
    'IBMCloud-config-2': {
        'ds': 'IBMCloud',
        'mocks': [
            MOCK_VIRT_IS_XEN,
            {'name': 'is_ibm_provisioning', 'ret': shell_false},
            {'name': 'blkid', 'ret': 0,
             'out': blkid_out(
                 [{'DEVNAME': 'xvda1', 'TYPE': 'ext3', 'PARTUUID': uuid4(),
                   'UUID': uuid4(), 'LABEL': 'cloudimg-bootfs'},
                  {'DEVNAME': 'xvdb', 'TYPE': 'vfat', 'LABEL': 'config-2',
                   'UUID': ds_ibm.IBM_CONFIG_UUID},
                  {'DEVNAME': 'xvda2', 'TYPE': 'ext4',
                   'LABEL': 'cloudimg-rootfs', 'PARTUUID': uuid4(),
                   'UUID': uuid4()},
                  ]),
             },
        ],
    },
    'IBMCloud-nodisks': {
        'ds': 'IBMCloud',
        'mocks': [
            MOCK_VIRT_IS_XEN,
            {'name': 'is_ibm_provisioning', 'ret': shell_false},
            {'name': 'blkid', 'ret': 0,
             'out': blkid_out(
                 [{'DEVNAME': 'xvda1', 'TYPE': 'vfat', 'PARTUUID': uuid4()},
                  {'DEVNAME': 'xvda2', 'TYPE': 'ext4',
                   'LABEL': 'cloudimg-rootfs', 'PARTUUID': uuid4()}]),
             },
        ],
    },
    'Oracle': {
        'ds': 'Oracle',
        'files': {
            P_CHASSIS_ASSET_TAG: ds_oracle.CHASSIS_ASSET_TAG + '\n',
        }
    },
    'SmartOS-bhyve': {
        'ds': 'SmartOS',
        'mocks': [
            MOCK_VIRT_IS_VM_OTHER,
            {'name': 'blkid', 'ret': 0,
             'out': blkid_out(
                 [{'DEVNAME': 'vda1', 'TYPE': 'ext4',
                   'PARTUUID': '49ec635a-01'},
                  {'DEVNAME': 'vda2', 'TYPE': 'swap',
                   'LABEL': 'cloudimg-swap', 'PARTUUID': '49ec635a-02'}]),
             },
        ],
        'files': {P_PRODUCT_NAME: 'SmartDC HVM\n'},
    },
    'SmartOS-lxbrand': {
        'ds': 'SmartOS',
        'mocks': [
            MOCK_VIRT_IS_CONTAINER_OTHER,
            {'name': 'uname', 'ret': 0,
             'out': ("Linux d43da87a-daca-60e8-e6d4-d2ed372662a3 4.3.0 "
                     "BrandZ virtual linux x86_64 GNU/Linux")},
            {'name': 'blkid', 'ret': 2, 'out': ''},
        ],
        'files': {ds_smartos.METADATA_SOCKFILE: 'would be a socket\n'},
    }

}

# vi: ts=4 expandtab
