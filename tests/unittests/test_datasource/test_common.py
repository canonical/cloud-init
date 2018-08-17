# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import settings
from cloudinit import sources
from cloudinit import type_utils
from cloudinit.sources import (
    DataSourceAliYun as AliYun,
    DataSourceAltCloud as AltCloud,
    DataSourceAzure as Azure,
    DataSourceBigstep as Bigstep,
    DataSourceCloudSigma as CloudSigma,
    DataSourceCloudStack as CloudStack,
    DataSourceConfigDrive as ConfigDrive,
    DataSourceDigitalOcean as DigitalOcean,
    DataSourceEc2 as Ec2,
    DataSourceGCE as GCE,
    DataSourceHetzner as Hetzner,
    DataSourceIBMCloud as IBMCloud,
    DataSourceMAAS as MAAS,
    DataSourceNoCloud as NoCloud,
    DataSourceOpenNebula as OpenNebula,
    DataSourceOpenStack as OpenStack,
    DataSourceOracle as Oracle,
    DataSourceOVF as OVF,
    DataSourceScaleway as Scaleway,
    DataSourceSmartOS as SmartOS,
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
    Ec2.DataSourceEc2Local,
    OpenStack.DataSourceOpenStackLocal,
    Scaleway.DataSourceScaleway,
]

DEFAULT_NETWORK = [
    AliYun.DataSourceAliYun,
    AltCloud.DataSourceAltCloud,
    Bigstep.DataSourceBigstep,
    CloudStack.DataSourceCloudStack,
    DSNone.DataSourceNone,
    Ec2.DataSourceEc2,
    GCE.DataSourceGCE,
    MAAS.DataSourceMAAS,
    NoCloud.DataSourceNoCloudNet,
    OpenStack.DataSourceOpenStack,
    OVF.DataSourceOVFNet,
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


# vi: ts=4 expandtab
