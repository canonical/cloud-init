# This file is part of cloud-init. See LICENSE file for license information.

import logging
from pathlib import Path
from unittest import mock

import pytest
from configobj import ConfigObj

from cloudinit import util
from cloudinit.config import cc_set_hostname
from cloudinit.sources.DataSourceNone import DataSourceNone
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


def fake_subp(*args, **kwargs):
    if args[0][0] in ["hostname", "hostnamectl"]:
        return None, None
    raise RuntimeError(f"Unexpected subp: {args[0]}")


def conf_parser(conf):
    return dict(ConfigObj(conf.splitlines()))


@pytest.mark.usefixtures("fake_filesystem")
class TestHostname:
    @pytest.fixture(autouse=True)
    def common_mocks(self, mocker):
        mocker.patch(
            "cloudinit.distros.debian.subp.subp", side_effect=fake_subp
        )

    @pytest.mark.parametrize(
        "distro_name,cfg,host_path,parser,expected",
        (
            pytest.param(
                "debian",
                {"hostname": "blah", "fqdn": "blah.example.com"},
                "/etc/hostname",
                lambda x: x,
                "blah",
                id="debian",
            ),
            pytest.param(
                "debian",
                {
                    "hostname": "blah",
                    "prefer_fqdn_over_hostname": True,
                    "fqdn": "blah.example.com",
                },
                "/etc/hostname",
                lambda x: x,
                "blah.example.com",
                id="debian_prefer_fqdn",
            ),
            pytest.param(
                "rhel",
                {"hostname": "blah", "fqdn": "blah.example.com"},
                "/etc/sysconfig/network",
                conf_parser,
                {"HOSTNAME": "blah.example.com"},
                id="rhel",
            ),
            pytest.param(
                "rhel",
                {
                    "hostname": "blah",
                    "prefer_fqdn_over_hostname": False,
                    "fqdn": "blah.example.com",
                },
                "/etc/sysconfig/network",
                conf_parser,
                {"HOSTNAME": "blah"},
                id="rhel_prefer_hostname",
            ),
            pytest.param(
                "sles",
                {"hostname": "blah", "fqdn": "blah.example.com"},
                "/etc/HOSTNAME",
                lambda x: x,
                "blah",
                id="sles",
            ),
        ),
    )
    def test_write_hostname(
        self,
        distro_name,
        cfg,
        host_path,
        parser,
        expected,
        paths,
        mocker,
    ):
        mocker.patch(
            "cloudinit.distros.Distro.uses_systemd", return_value=False
        )
        cc = get_cloud(distro=distro_name, paths=paths, sys_cfg=cfg)
        cc_set_hostname.handle("cc_set_hostname", cfg, cc, [])
        contents = util.load_text_file(host_path).strip()
        assert expected == parser(contents)

    @mock.patch("cloudinit.distros.photon.subp.subp")
    def test_photon_hostname(self, m_subp, paths):
        cfg1 = {
            "hostname": "photon",
            "prefer_fqdn_over_hostname": True,
            "fqdn": "test1.vmware.com",
        }
        cfg2 = {
            "hostname": "photon",
            "prefer_fqdn_over_hostname": False,
            "fqdn": "test2.vmware.com",
        }

        m_subp.return_value = (None, None)
        cc = get_cloud(distro="photon", paths=paths, sys_cfg=cfg1)
        for c in [cfg1, cfg2]:
            cc_set_hostname.handle("cc_set_hostname", c, cc, [])
            print("\n", m_subp.call_args_list)
            if c["prefer_fqdn_over_hostname"]:
                assert [
                    mock.call(
                        ["hostnamectl", "set-hostname", c["fqdn"]],
                        capture=True,
                    )
                ] in m_subp.call_args_list
                assert [
                    mock.call(
                        ["hostnamectl", "set-hostname", c["hostname"]],
                        capture=True,
                    )
                ] not in m_subp.call_args_list
            else:
                assert [
                    mock.call(
                        ["hostnamectl", "set-hostname", c["hostname"]],
                        capture=True,
                    )
                ] in m_subp.call_args_list
                assert [
                    mock.call(
                        ["hostnamectl", "set-hostname", c["fqdn"]],
                        capture=True,
                    )
                ] not in m_subp.call_args_list

    @mock.patch("cloudinit.util.get_hostname", return_value="localhost")
    def test_multiple_calls_skips_unchanged_hostname(
        self, get_hostname, paths, caplog
    ):
        """Only new hostname or fqdn values will generate a hostname call."""
        cc = get_cloud(distro="debian", paths=paths)
        cc_set_hostname.handle(
            "cc_set_hostname", {"hostname": "hostname1.me.com"}, cc, []
        )
        contents = util.load_text_file("/etc/hostname")
        assert "hostname1" == contents.strip()
        cc_set_hostname.handle(
            "cc_set_hostname", {"hostname": "hostname1.me.com"}, cc, []
        )
        assert "No hostname changes. Skipping set_hostname\n" in caplog.text
        cc_set_hostname.handle(
            "cc_set_hostname", {"hostname": "hostname2.me.com"}, cc, []
        )
        contents = util.load_text_file("/etc/hostname")
        assert "hostname2" == contents.strip()
        assert (
            "Non-persistently setting the system hostname to hostname2"
            in caplog.text
        )

    @mock.patch("cloudinit.util.get_hostname", return_value="localhost")
    def test_localhost_default_hostname(self, get_hostname, paths):
        """
        No hostname set. Default value returned is localhost,
        but we shouldn't write it in /etc/hostname
        """
        cc = get_cloud(distro="debian", paths=paths, ds=DataSourceNone)

        util.write_file("/etc/hostname", "")
        cc_set_hostname.handle("cc_set_hostname", {}, cc, [])
        contents = util.load_text_file("/etc/hostname")
        assert "" == contents.strip()

    @mock.patch("cloudinit.util.get_hostname", return_value="localhost")
    def test_localhost_user_given_hostname(self, get_hostname, paths):
        """
        User set hostname is localhost. We should write it in /etc/hostname
        """
        cc = get_cloud(distro="debian", paths=paths, ds=DataSourceNone)

        # user-provided localhost should not be ignored
        util.write_file("/etc/hostname", "")
        cc_set_hostname.handle(
            "cc_set_hostname", {"hostname": "localhost"}, cc, []
        )
        contents = util.load_text_file("/etc/hostname")
        assert "localhost" == contents.strip()

    def test_error_on_distro_set_hostname_errors(self, paths):
        """Raise SetHostnameError on exceptions from distro.set_hostname."""

        def set_hostname_error(hostname, fqdn=None) -> None:
            raise RuntimeError(f"OOPS on: {fqdn}")

        cc = get_cloud(distro="debian", paths=paths)
        cc.distro.set_hostname = set_hostname_error
        with pytest.raises(cc_set_hostname.SetHostnameError) as exc_info:
            cc_set_hostname.handle(
                "somename", {"hostname": "hostname1.me.com"}, cc, []
            )
        assert (
            "Failed to set the hostname to hostname1.me.com (hostname1):"
            " OOPS on: hostname1.me.com" == str(exc_info.value)
        )

    def test_ignore_empty_previous_artifact_file(self, paths):
        cfg = {
            "hostname": "blah",
            "fqdn": "blah.blah.blah.yahoo.com",
        }
        cc = get_cloud(distro="debian", paths=paths)
        prev_fn = Path(cc.get_cpath("data")) / "set-hostname"
        prev_fn.parent.mkdir()
        prev_fn.touch()
        cc_set_hostname.handle("cc_set_hostname", cfg, cc, [])
        contents = util.load_text_file("/etc/hostname")
        assert "blah" == contents.strip()

    @pytest.mark.parametrize(
        "distro_name",
        (
            "debian",
            "arch",
            "alpine",
            "gentoo",
            "photon",
            "rhel",
        ),
    )
    def test_create_hostname_file_false(self, distro_name, paths):
        cfg = {
            "hostname": "foo",
            "fqdn": "foo.blah.yahoo.com",
            "create_hostname_file": False,
        }
        cc = get_cloud(distro=distro_name, paths=paths)
        cc_set_hostname.handle("cc_set_hostname", cfg, cc, [])
        with pytest.raises(FileNotFoundError):
            util.load_text_file("/etc/hostname")
