# This file is part of cloud-init. See LICENSE file for license information.
from unittest import mock

from cloudinit import cloud, distros, helpers
from cloudinit.net.dhcp import IscDhclient
from cloudinit.sources import DataSource, DataSourceHostname
from cloudinit.sources.DataSourceNone import DataSourceNone


def get_cloud(
    distro=None, paths=None, sys_cfg=None, metadata=None, mocked_distro=False
):
    """Obtain a "cloud" that can be used for testing.

    Modules take a 'cloud' parameter to call into things that are
    datasource/distro specific. In most cases, the specifics of this cloud
    implementation aren't needed to test the module, so provide a fake
    datasource/distro with stubbed calls to methods that may attempt to
    read/write files or shell out. If a specific distro is needed, it can
    be passed in as the distro parameter.
    """
    paths = paths or helpers.Paths({})
    sys_cfg = sys_cfg or {}
    cls = distros.fetch(distro) if distro else MockDistro
    # *BSD calls platform.system to determine osfamilies
    osfamily = distro.lower() if distro else "ubuntu"
    with mock.patch("platform.system", return_value=osfamily):
        mydist = cls(distro, sys_cfg, paths)
    if mocked_distro:
        mydist = mock.MagicMock(wraps=mydist)
    myds = DataSourceTesting(sys_cfg, mydist, paths)
    if metadata:
        myds.metadata.update(metadata)
    if paths:
        paths.datasource = myds
    return cloud.Cloud(
        myds, paths, sys_cfg, mydist, runners=helpers.Runners(paths)
    )


def abstract_to_concrete(abclass):
    """Takes an abstract class and returns a concrete version of it."""

    class concreteCls(abclass):
        pass

    concreteCls.__abstractmethods__ = frozenset()
    return type("DummyConcrete" + abclass.__name__, (concreteCls,), {})


class DataSourceTesting(DataSourceNone):
    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        return DataSourceHostname("hostname", False)

    def persist_instance_data(self):
        return True

    @property
    def cloud_name(self):
        return "testing"


class MockDistro(distros.Distro):
    # MockDistro is here to test base Distro class implementations
    def __init__(self, name="testingdistro", cfg=None, paths=None):
        self._client = None
        if not cfg:
            cfg = {}
        if not paths:
            paths = {}
        super(MockDistro, self).__init__(name, cfg, paths)

    @property
    def dhcp_client(self):
        if not self._client:
            with mock.patch(
                "cloudinit.net.dhcp.subp.which", return_value=True
            ):
                self._client = IscDhclient()
        return self._client

    def install_packages(self, pkglist):
        pass

    def set_hostname(self, hostname, fqdn=None):
        pass

    @staticmethod
    def uses_systemd():
        return True

    @staticmethod
    def get_proc_ppid(_):
        return 1

    @staticmethod
    def get_proc_pgid(_):
        return 99999

    def get_primary_arch(self):
        return "i386"

    def get_package_mirror_info(self, arch=None, data_source=None):
        pass

    def generate_fallback_config(self):
        return {}

    def apply_network_config(self, netconfig, bring_up=False) -> bool:
        return False

    def apply_locale(self, locale, out_fn=None):
        pass

    def set_timezone(self, tz):
        pass

    def _read_hostname(self, filename, default=None):
        raise NotImplementedError()

    def _write_hostname(self, hostname, filename):
        raise NotImplementedError()

    def _read_system_hostname(self):
        raise NotImplementedError()

    def update_hostname(self, hostname, fqdn, prev_hostname_fn):
        pass

    def update_etc_hosts(self, hostname, fqdn):
        pass

    def add_user(self, name, **kwargs):
        pass

    def add_snap_user(self, name, **kwargs):
        return "snap_user"

    def create_user(self, name, **kwargs):
        return True

    def lock_passwd(self, name):
        pass

    def expire_passwd(self, user):
        pass

    def set_passwd(self, user, passwd, hashed=False):
        return True

    def ensure_sudo_dir(self, path, sudo_base="/etc/sudoers"):
        pass

    def write_sudo_rules(self, user, rules, sudo_file=None):
        pass

    def create_group(self, name, members=None):
        pass

    def shutdown_command(self, *, mode, delay, message):
        pass

    def package_command(self, command, args=None, pkgs=None):
        pass

    def update_package_sources(self, *, force=False):
        return (True, "yay")

    def do_as(self, command, args=None, **kwargs):
        return ("stdout", "stderr")


TEST_INSTANCE_ID = "i-testing"


class FakeDataSource(DataSource):
    def __init__(
        self,
        userdata=None,
        vendordata=None,
        vendordata2=None,
        network_config="",
        paths=None,
    ):
        DataSource.__init__(self, {}, None, paths=paths)
        self.metadata = {"instance-id": TEST_INSTANCE_ID}
        self.userdata_raw = userdata
        self.vendordata_raw = vendordata
        self.vendordata2_raw = vendordata2
        self._network_config = None
        if network_config:  # Permit for None value to setup attribute
            self._network_config = network_config

    @property
    def network_config(self):
        return self._network_config

    def _get_data(self):
        return True
