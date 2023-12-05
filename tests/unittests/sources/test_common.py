# This file is part of cloud-init. See LICENSE file for license information.

from unittest.mock import patch

from cloudinit import importer, settings, sources, type_utils
from cloudinit.sources import DataSource
from cloudinit.sources import DataSourceAkamai as Akamai
from cloudinit.sources import DataSourceAliYun as AliYun
from cloudinit.sources import DataSourceAltCloud as AltCloud
from cloudinit.sources import DataSourceAzure as Azure
from cloudinit.sources import DataSourceBigstep as Bigstep
from cloudinit.sources import DataSourceCloudSigma as CloudSigma
from cloudinit.sources import DataSourceCloudStack as CloudStack
from cloudinit.sources import DataSourceConfigDrive as ConfigDrive
from cloudinit.sources import DataSourceDigitalOcean as DigitalOcean
from cloudinit.sources import DataSourceEc2 as Ec2
from cloudinit.sources import DataSourceExoscale as Exoscale
from cloudinit.sources import DataSourceGCE as GCE
from cloudinit.sources import DataSourceHetzner as Hetzner
from cloudinit.sources import DataSourceIBMCloud as IBMCloud
from cloudinit.sources import DataSourceLXD as LXD
from cloudinit.sources import DataSourceMAAS as MAAS
from cloudinit.sources import DataSourceNoCloud as NoCloud
from cloudinit.sources import DataSourceNone as DSNone
from cloudinit.sources import DataSourceNWCS as NWCS
from cloudinit.sources import DataSourceOpenNebula as OpenNebula
from cloudinit.sources import DataSourceOpenStack as OpenStack
from cloudinit.sources import DataSourceOracle as Oracle
from cloudinit.sources import DataSourceOVF as OVF
from cloudinit.sources import DataSourceRbxCloud as RbxCloud
from cloudinit.sources import DataSourceScaleway as Scaleway
from cloudinit.sources import DataSourceSmartOS as SmartOS
from cloudinit.sources import DataSourceUpCloud as UpCloud
from cloudinit.sources import DataSourceVMware as VMware
from cloudinit.sources import DataSourceVultr as Vultr
from tests.unittests import helpers as test_helpers

DEFAULT_LOCAL = [
    AliYun.DataSourceAliYunLocal,
    Azure.DataSourceAzure,
    CloudSigma.DataSourceCloudSigma,
    ConfigDrive.DataSourceConfigDrive,
    DigitalOcean.DataSourceDigitalOcean,
    GCE.DataSourceGCELocal,
    Hetzner.DataSourceHetzner,
    IBMCloud.DataSourceIBMCloud,
    LXD.DataSourceLXD,
    MAAS.DataSourceMAAS,
    NoCloud.DataSourceNoCloud,
    OpenNebula.DataSourceOpenNebula,
    Oracle.DataSourceOracle,
    OVF.DataSourceOVF,
    SmartOS.DataSourceSmartOS,
    Vultr.DataSourceVultr,
    Ec2.DataSourceEc2Local,
    OpenStack.DataSourceOpenStackLocal,
    RbxCloud.DataSourceRbxCloud,
    Scaleway.DataSourceScaleway,
    UpCloud.DataSourceUpCloudLocal,
    VMware.DataSourceVMware,
    NWCS.DataSourceNWCS,
    Akamai.DataSourceAkamaiLocal,
]

DEFAULT_NETWORK = [
    AliYun.DataSourceAliYun,
    AltCloud.DataSourceAltCloud,
    Bigstep.DataSourceBigstep,
    CloudStack.DataSourceCloudStack,
    DSNone.DataSourceNone,
    Ec2.DataSourceEc2,
    Exoscale.DataSourceExoscale,
    GCE.DataSourceGCE,
    MAAS.DataSourceMAAS,
    NoCloud.DataSourceNoCloudNet,
    OpenStack.DataSourceOpenStack,
    OVF.DataSourceOVFNet,
    UpCloud.DataSourceUpCloud,
    Akamai.DataSourceAkamai,
    VMware.DataSourceVMware,
]


class ExpectedDataSources(test_helpers.TestCase):
    builtin_list = settings.CFG_BUILTIN["datasource_list"]
    deps_local = [sources.DEP_FILESYSTEM]
    deps_network = [sources.DEP_FILESYSTEM, sources.DEP_NETWORK]
    pkg_list = [type_utils.obj_name(sources)]

    @patch.object(
        importer,
        "match_case_insensitive_module_name",
        lambda name: f"DataSource{name}",
    )
    def test_expected_default_local_sources_found(self):
        found = sources.list_sources(
            self.builtin_list,
            self.deps_local,
            self.pkg_list,
        )
        self.assertEqual(set(DEFAULT_LOCAL), set(found))

    @patch.object(
        importer,
        "match_case_insensitive_module_name",
        lambda name: f"DataSource{name}",
    )
    def test_expected_default_network_sources_found(self):
        found = sources.list_sources(
            self.builtin_list,
            self.deps_network,
            self.pkg_list,
        )
        self.assertEqual(set(DEFAULT_NETWORK), set(found))

    @patch.object(
        importer,
        "match_case_insensitive_module_name",
        lambda name: f"DataSource{name}",
    )
    def test_expected_nondefault_network_sources_found(self):
        found = sources.list_sources(
            ["AliYun"],
            self.deps_network,
            self.pkg_list,
        )
        self.assertEqual(set([AliYun.DataSourceAliYun]), set(found))


class TestDataSourceInvariants(test_helpers.TestCase):
    def test_data_sources_have_valid_network_config_sources(self):
        for ds in DEFAULT_LOCAL + DEFAULT_NETWORK:
            for cfg_src in ds.network_config_sources:
                fail_msg = (
                    "{} has an invalid network_config_sources entry:"
                    " {}".format(str(ds), cfg_src)
                )
                self.assertTrue(
                    isinstance(cfg_src, sources.NetworkConfigSource), fail_msg
                )

    def test_expected_dsname_defined(self):
        for ds in DEFAULT_LOCAL + DEFAULT_NETWORK:
            fail_msg = (
                "{} has an invalid / missing dsname property: {}".format(
                    str(ds), str(ds.dsname)
                )
            )
            self.assertNotEqual(ds.dsname, DataSource.dsname, fail_msg)
            self.assertIsNotNone(ds.dsname)
