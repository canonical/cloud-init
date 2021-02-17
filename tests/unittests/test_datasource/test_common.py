# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import settings
from cloudinit import sources
from cloudinit import type_utils
from cloudinit.sources import (
    DataSource,
    DataSourceAliYun as AliYun,
    DataSourceAltCloud as AltCloud,
    DataSourceAzure as Azure,
    DataSourceBigstep as Bigstep,
    DataSourceCloudSigma as CloudSigma,
    DataSourceCloudStack as CloudStack,
    DataSourceConfigDrive as ConfigDrive,
    DataSourceDigitalOcean as DigitalOcean,
    DataSourceEc2 as Ec2,
    DataSourceExoscale as Exoscale,
    DataSourceGCE as GCE,
    DataSourceHetzner as Hetzner,
    DataSourceIBMCloud as IBMCloud,
    DataSourceMAAS as MAAS,
    DataSourceNoCloud as NoCloud,
    DataSourceOpenNebula as OpenNebula,
    DataSourceOpenStack as OpenStack,
    DataSourceOracle as Oracle,
    DataSourceOVF as OVF,
    DataSourceRbxCloud as RbxCloud,
    DataSourceScaleway as Scaleway,
    DataSourceSmartOS as SmartOS,
    DataSourceVultr as Vultr,
)
from cloudinit.sources import DataSourceNone as DSNone

from cloudinit.tests import helpers as test_helpers

DEFAULT_LOCAL = [
    Azure.DataSourceAzure,
    CloudSigma.DataSourceCloudSigma,
    ConfigDrive.DataSourceConfigDrive,
    DigitalOcean.DataSourceDigitalOcean,
    Hetzner.DataSourceHetzner,
    IBMCloud.DataSourceIBMCloud,
    NoCloud.DataSourceNoCloud,
    OpenNebula.DataSourceOpenNebula,
    Oracle.DataSourceOracle,
    OVF.DataSourceOVF,
    SmartOS.DataSourceSmartOS,
    Vultr.DataSourceVultr,
    Ec2.DataSourceEc2Local,
    OpenStack.DataSourceOpenStackLocal,
    RbxCloud.DataSourceRbxCloud,
    Scaleway.DataSourceScaleway
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
    OVF.DataSourceOVFNet
]


class ExpectedDataSources(test_helpers.TestCase):
    builtin_list = settings.CFG_BUILTIN['datasource_list']
    deps_local = [sources.DEP_FILESYSTEM]
    deps_network = [sources.DEP_FILESYSTEM, sources.DEP_NETWORK]
    pkg_list = [type_utils.obj_name(sources)]

    def test_expected_default_local_sources_found(self):
        found = sources.list_sources(
            self.builtin_list, self.deps_local, self.pkg_list)
        self.assertEqual(set(DEFAULT_LOCAL), set(found))

    def test_expected_default_network_sources_found(self):
        found = sources.list_sources(
            self.builtin_list, self.deps_network, self.pkg_list)
        self.assertEqual(set(DEFAULT_NETWORK), set(found))

    def test_expected_nondefault_network_sources_found(self):
        found = sources.list_sources(
            ['AliYun'], self.deps_network, self.pkg_list)
        self.assertEqual(set([AliYun.DataSourceAliYun]), set(found))


class TestDataSourceInvariants(test_helpers.TestCase):
    def test_data_sources_have_valid_network_config_sources(self):
        for ds in DEFAULT_LOCAL + DEFAULT_NETWORK:
            for cfg_src in ds.network_config_sources:
                fail_msg = ('{} has an invalid network_config_sources entry:'
                            ' {}'.format(str(ds), cfg_src))
                self.assertTrue(hasattr(sources.NetworkConfigSource, cfg_src),
                                fail_msg)

    def test_expected_dsname_defined(self):
        for ds in DEFAULT_LOCAL + DEFAULT_NETWORK:
            fail_msg = (
                '{} has an invalid / missing dsname property: {}'.format(
                    str(ds), str(ds.dsname)
                )
            )
            self.assertNotEqual(ds.dsname, DataSource.dsname, fail_msg)
            self.assertIsNotNone(ds.dsname)

# vi: ts=4 expandtab
