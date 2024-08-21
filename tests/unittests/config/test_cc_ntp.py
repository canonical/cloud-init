# This file is part of cloud-init. See LICENSE file for license information.
import copy
import os
import re
import shutil
from functools import partial
from os.path import dirname

import pytest

from cloudinit import helpers, util
from cloudinit.config import cc_ntp
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    CiTestCase,
    FilesystemMockingTestCase,
    mock,
    skipUnlessJsonSchema,
)
from tests.unittests.util import get_cloud

NTP_TEMPLATE = """\
## template: jinja
servers {{servers}}
pools {{pools}}
"""

TIMESYNCD_TEMPLATE = """\
## template:jinja
[Time]
{% if servers or pools -%}
NTP={% for host in servers|list + pools|list %}{{ host }} {% endfor -%}
{% endif -%}
"""


class TestNtp(FilesystemMockingTestCase):
    with_logs = True

    def setUp(self):
        super(TestNtp, self).setUp()
        self.new_root = self.tmp_dir()
        self.add_patch("cloudinit.util.system_is_snappy", "m_snappy")
        self.m_snappy.return_value = False
        self.new_root = self.reRoot()
        self._get_cloud = partial(
            get_cloud, paths=helpers.Paths({"templates_dir": self.new_root})
        )

    def _get_template_path(self, template_name, distro, basepath=None):
        # ntp.conf.{distro} -> ntp.conf.debian.tmpl
        template_fn = "{0}.tmpl".format(
            template_name.replace("{distro}", distro)
        )
        if not basepath:
            basepath = self.new_root
        path = os.path.join(basepath, template_fn)
        return path

    def _generate_template(self, template=None):
        if not template:
            template = NTP_TEMPLATE
        confpath = os.path.join(self.new_root, "client.conf")
        template_fn = os.path.join(self.new_root, "client.conf.tmpl")
        util.write_file(template_fn, content=template)
        return (confpath, template_fn)

    def _mock_ntp_client_config(self, client=None, distro=None):
        if not client:
            client = "ntp"
        if not distro:
            distro = "ubuntu"
        dcfg = cc_ntp.distro_ntp_client_configs(distro)
        if client == "systemd-timesyncd":
            template = TIMESYNCD_TEMPLATE
        else:
            template = NTP_TEMPLATE
        (confpath, _template_fn) = self._generate_template(template=template)
        ntpconfig = copy.deepcopy(dcfg[client])
        ntpconfig["confpath"] = confpath
        ntpconfig["template_name"] = os.path.basename(confpath)
        return ntpconfig

    @mock.patch("cloudinit.config.cc_ntp.subp")
    def test_ntp_install(self, mock_subp):
        """ntp_install_client runs install_func when check_exe is absent."""
        mock_subp.which.return_value = None  # check_exe not found.
        install_func = mock.MagicMock()
        cc_ntp.install_ntp_client(
            install_func, packages=["ntpx"], check_exe="ntpdx"
        )
        mock_subp.which.assert_called_with("ntpdx")
        install_func.assert_called_once_with(["ntpx"])

    @mock.patch("cloudinit.config.cc_ntp.subp")
    def test_ntp_install_not_needed(self, mock_subp):
        """ntp_install_client doesn't install when check_exe is found."""
        client = "chrony"
        mock_subp.which.return_value = [client]  # check_exe found.
        install_func = mock.MagicMock()
        cc_ntp.install_ntp_client(
            install_func, packages=[client], check_exe=client
        )
        install_func.assert_not_called()

    @mock.patch("cloudinit.config.cc_ntp.subp")
    def test_ntp_install_no_op_with_empty_pkg_list(self, mock_subp):
        """ntp_install_client runs install_func with empty list"""
        mock_subp.which.return_value = None  # check_exe not found
        install_func = mock.MagicMock()
        cc_ntp.install_ntp_client(
            install_func, packages=[], check_exe="timesyncd"
        )
        install_func.assert_called_once_with([])

    def test_ntp_rename_ntp_conf(self):
        """When NTP_CONF exists, rename_ntp moves it."""
        ntpconf = self.tmp_path("ntp.conf", self.new_root)
        util.write_file(ntpconf, "")
        cc_ntp.rename_ntp_conf(confpath=ntpconf)
        self.assertFalse(os.path.exists(ntpconf))
        self.assertTrue(os.path.exists("{0}.dist".format(ntpconf)))

    def test_ntp_rename_ntp_conf_skip_missing(self):
        """When NTP_CONF doesn't exist rename_ntp doesn't create a file."""
        ntpconf = self.tmp_path("ntp.conf", self.new_root)
        self.assertFalse(os.path.exists(ntpconf))
        cc_ntp.rename_ntp_conf(confpath=ntpconf)
        self.assertFalse(os.path.exists("{0}.dist".format(ntpconf)))
        self.assertFalse(os.path.exists(ntpconf))

    def test_write_ntp_config_template_uses_ntp_conf_distro_no_servers(self):
        """write_ntp_config_template reads from $client.conf.distro.tmpl"""
        servers = []
        pools = ["10.0.0.1", "10.0.0.2"]
        (confpath, template_fn) = self._generate_template()
        cc_ntp.write_ntp_config_template(
            "ubuntu",
            servers=servers,
            pools=pools,
            path=confpath,
            template_fn=template_fn,
            template=None,
        )
        self.assertEqual(
            "servers []\npools ['10.0.0.1', '10.0.0.2']\n",
            util.load_text_file(confpath),
        )

    def test_write_ntp_config_template_defaults_pools_w_empty_lists(self):
        """write_ntp_config_template defaults pools servers upon empty config.

        When both pools and servers are empty, default NR_POOL_SERVERS get
        configured.
        """
        distro = "ubuntu"
        pools = cc_ntp.generate_server_names(distro)
        servers = []
        (confpath, template_fn) = self._generate_template()
        cc_ntp.write_ntp_config_template(
            distro,
            servers=servers,
            pools=pools,
            path=confpath,
            template_fn=template_fn,
            template=None,
        )
        self.assertEqual(
            "servers []\npools {0}\n".format(pools),
            util.load_text_file(confpath),
        )

    def test_defaults_pools_empty_lists_sles(self):
        """write_ntp_config_template defaults opensuse pools upon empty config.

        When both pools and servers are empty, default NR_POOL_SERVERS get
        configured.
        """
        distro = "sles"
        default_pools = cc_ntp.generate_server_names(distro)
        (confpath, template_fn) = self._generate_template()

        cc_ntp.write_ntp_config_template(
            distro,
            servers=[],
            pools=[],
            path=confpath,
            template_fn=template_fn,
            template=None,
        )
        for pool in default_pools:
            self.assertIn("opensuse", pool)
        self.assertEqual(
            "servers []\npools {0}\n".format(default_pools),
            util.load_text_file(confpath),
        )
        self.assertIn(
            "Adding distro default ntp pool servers: {0}".format(
                ",".join(default_pools)
            ),
            self.logs.getvalue(),
        )

    def test_timesyncd_template(self):
        """Test timesycnd template is correct"""
        pools = ["0.mycompany.pool.ntp.org", "3.mycompany.pool.ntp.org"]
        servers = ["192.168.23.3", "192.168.23.4"]
        (confpath, template_fn) = self._generate_template(
            template=TIMESYNCD_TEMPLATE
        )
        cc_ntp.write_ntp_config_template(
            "ubuntu",
            servers=servers,
            pools=pools,
            path=confpath,
            template_fn=template_fn,
            template=None,
        )
        self.assertEqual(
            "[Time]\nNTP=%s %s \n" % (" ".join(servers), " ".join(pools)),
            util.load_text_file(confpath),
        )

    def test_distro_ntp_client_configs(self):
        """Test we have updated ntp client configs on different distros"""
        delta = copy.deepcopy(cc_ntp.DISTRO_CLIENT_CONFIG)
        base = copy.deepcopy(cc_ntp.NTP_CLIENT_CONFIG)
        # confirm no-delta distros match the base config
        for distro in cc_ntp.distros:
            if distro not in delta:
                result = cc_ntp.distro_ntp_client_configs(distro)
                self.assertEqual(base, result)
        # for distros with delta, ensure the merged config values match
        # what is set in the delta
        for distro in delta.keys():
            result = cc_ntp.distro_ntp_client_configs(distro)
            for client in delta[distro].keys():
                for key in delta[distro][client].keys():
                    self.assertEqual(
                        delta[distro][client][key], result[client][key]
                    )

    def _get_expected_pools(self, pools, distro, client):
        expected_pools = None
        if client in ["ntp", "chrony"]:
            if client == "ntp" and distro == "alpine":
                # NTP for Alpine Linux is Busybox's ntp which does not
                # support 'pool' lines in its configuration file.
                expected_pools = []
            else:
                expected_pools = [
                    "pool {0} iburst".format(pool) for pool in pools
                ]
        elif client == "systemd-timesyncd":
            expected_pools = " ".join(pools)

        return expected_pools

    def _get_expected_servers(self, servers, distro, client):
        expected_servers = None
        if client in ["ntp", "chrony"]:
            if client == "ntp" and distro == "alpine":
                # NTP for Alpine Linux is Busybox's ntp which only supports
                # 'server' lines without iburst option.
                expected_servers = [
                    "server {0}".format(srv) for srv in servers
                ]
            else:
                expected_servers = [
                    "server {0} iburst".format(srv) for srv in servers
                ]
        elif client == "systemd-timesyncd":
            expected_servers = " ".join(servers)

        return expected_servers

    def test_ntp_handler_real_distro_ntp_templates(self):
        """Test ntp handler renders the shipped distro ntp client templates."""
        pools = ["0.mycompany.pool.ntp.org", "3.mycompany.pool.ntp.org"]
        servers = ["192.168.23.3", "192.168.23.4"]
        for client in ["ntp", "systemd-timesyncd", "chrony"]:
            for distro in cc_ntp.distros:
                distro_cfg = cc_ntp.distro_ntp_client_configs(distro)
                ntpclient = distro_cfg[client]
                confpath = os.path.join(
                    self.new_root, ntpclient.get("confpath")[1:]
                )
                template = ntpclient.get("template_name")
                # find sourcetree template file
                root_dir = (
                    dirname(dirname(os.path.realpath(util.__file__)))
                    + "/templates"
                )
                source_fn = self._get_template_path(
                    template, distro, basepath=root_dir
                )
                template_fn = self._get_template_path(template, distro)
                # don't fail if cloud-init doesn't have a template for
                # a distro,client pair
                if not os.path.exists(source_fn):
                    continue
                # Create a copy in our tmp_dir
                shutil.copy(source_fn, template_fn)
                cc_ntp.write_ntp_config_template(
                    distro,
                    servers=servers,
                    pools=pools,
                    path=confpath,
                    template_fn=template_fn,
                )
                content = util.load_text_file(confpath)
                if client in ["ntp", "chrony"]:
                    content_lines = content.splitlines()
                    expected_servers = self._get_expected_servers(
                        servers, distro, client
                    )
                    print("distro=%s client=%s" % (distro, client))
                    for sline in expected_servers:
                        self.assertIn(
                            sline,
                            content_lines,
                            "failed to render {0} conf for distro:{1}".format(
                                client, distro
                            ),
                        )
                    expected_pools = self._get_expected_pools(
                        pools, distro, client
                    )
                    if expected_pools != []:
                        for pline in expected_pools:
                            self.assertIn(
                                pline,
                                content_lines,
                                "failed to render {0} conf"
                                " for distro:{1}".format(client, distro),
                            )
                elif client == "systemd-timesyncd":
                    expected_servers = self._get_expected_servers(
                        servers, distro, client
                    )
                    expected_pools = self._get_expected_pools(
                        pools, distro, client
                    )
                    expected_content = (
                        "# cloud-init generated file\n"
                        "# See timesyncd.conf(5) for details.\n\n"
                        "[Time]\nNTP=%s %s \n"
                        % (expected_servers, expected_pools)
                    )
                    self.assertEqual(expected_content, content)

    def test_no_ntpcfg_does_nothing(self):
        """When no ntp section is defined handler logs a warning and noops."""
        cc_ntp.handle("cc_ntp", {}, None, [])
        self.assertEqual(
            "DEBUG: Skipping module named cc_ntp, "
            "not present or disabled by cfg\n",
            self.logs.getvalue(),
        )

    @mock.patch("cloudinit.config.cc_ntp.select_ntp_client")
    def test_ntp_handler_schema_validation_allows_empty_ntp_config(
        self, m_select
    ):
        """Ntp schema validation allows for an empty ntp: configuration."""
        valid_empty_configs = [{"ntp": {}}, {"ntp": None}]
        for valid_empty_config in valid_empty_configs:
            for distro in cc_ntp.distros:
                # skip the test if the distro is COS. As in COS, the default
                # config file is installed
                if distro == "cos":
                    return
                mycloud = self._get_cloud(distro)
                ntpconfig = self._mock_ntp_client_config(distro=distro)
                confpath = ntpconfig["confpath"]
                m_select.return_value = ntpconfig
                cc_ntp.handle("cc_ntp", valid_empty_config, mycloud, [])
                if distro == "alpine":
                    # _mock_ntp_client_config call above did not specify a
                    # client value and so it defaults to "ntp" which on
                    # Alpine Linux only supports servers and not pools.

                    servers = cc_ntp.generate_server_names(mycloud.distro.name)
                    self.assertEqual(
                        "servers {0}\npools []\n".format(servers),
                        util.load_text_file(confpath),
                    )
                else:
                    pools = cc_ntp.generate_server_names(mycloud.distro.name)
                    self.assertEqual(
                        "servers []\npools {0}\n".format(pools),
                        util.load_text_file(confpath),
                    )
            self.assertNotIn(
                "Invalid cloud-config provided:", self.logs.getvalue()
            )

    @mock.patch("cloudinit.config.cc_ntp.select_ntp_client")
    def test_ntp_handler_timesyncd(self, m_select):
        """Test ntp handler configures timesyncd"""
        servers = ["192.168.2.1", "192.168.2.2"]
        pools = ["0.mypool.org"]
        cfg = {"ntp": {"servers": servers, "pools": pools}}
        client = "systemd-timesyncd"
        for distro in cc_ntp.distros:
            mycloud = self._get_cloud(distro)
            ntpconfig = self._mock_ntp_client_config(
                distro=distro, client=client
            )
            confpath = ntpconfig["confpath"]
            m_select.return_value = ntpconfig
            cc_ntp.handle("cc_ntp", cfg, mycloud, [])
            self.assertEqual(
                "[Time]\nNTP=192.168.2.1 192.168.2.2 0.mypool.org \n",
                util.load_text_file(confpath),
            )

    @mock.patch("cloudinit.config.cc_ntp.select_ntp_client")
    def test_ntp_handler_enabled_false(self, m_select):
        """Test ntp handler does not run if enabled: false"""
        cfg = {"ntp": {"enabled": False}}
        for distro in cc_ntp.distros:
            mycloud = self._get_cloud(distro)
            cc_ntp.handle("notimportant", cfg, mycloud, None)
            self.assertEqual(0, m_select.call_count)

    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.subp.which", return_value=True)
    @mock.patch("cloudinit.config.cc_ntp.select_ntp_client")
    @mock.patch("cloudinit.distros.Distro.uses_systemd")
    def test_ntp_the_whole_package(self, m_sysd, m_select, m_which, m_subp):
        """Test enabled config renders template, and restarts service"""
        cfg = {"ntp": {"enabled": True}}
        for distro in cc_ntp.distros:
            m_subp.reset_mock()
            mycloud = self._get_cloud(distro)
            ntpconfig = self._mock_ntp_client_config(distro=distro)
            confpath = ntpconfig["confpath"]
            service_name = ntpconfig["service_name"]
            m_select.return_value = ntpconfig

            hosts = cc_ntp.generate_server_names(mycloud.distro.name)
            uses_systemd = True
            is_FreeBSD = False
            is_OpenBSD = False
            expected_service_call = [
                "systemctl",
                "reload-or-restart",
                service_name,
            ]
            expected_content = "servers []\npools {0}\n".format(hosts)

            # skip the test if the distro is COS. As in COS, the default
            # config file is installed
            if distro == "cos":
                return

            if distro == "alpine":
                uses_systemd = False
                expected_service_call = [
                    "rc-service",
                    "--nocolor",
                    service_name,
                    "restart",
                ]
                # _mock_ntp_client_config call above did not specify a client
                # value and so it defaults to "ntp" which on Alpine Linux only
                # supports servers and not pools.
                expected_content = "servers {0}\npools []\n".format(hosts)

            if distro == "freebsd":
                uses_systemd = False
                is_FreeBSD = True
                if service_name != "ntpd":
                    expected_service_call = ["service", "ntpd", "disable"]
                else:
                    expected_service_call = [
                        "service",
                        service_name,
                        "restart",
                    ]

            if distro == "openbsd":
                uses_systemd = False
                is_OpenBSD = True
                expected_service_call = ["rcctl", "restart", service_name]

            m_sysd.return_value = uses_systemd
            with mock.patch("cloudinit.config.cc_ntp.util") as m_util:
                # allow use of util.mergemanydict
                m_util.mergemanydict.side_effect = util.mergemanydict
                # use the config 'enabled' value
                m_util.is_false.return_value = util.is_false(
                    cfg["ntp"]["enabled"]
                )
                m_util.is_BSD.return_value = is_FreeBSD or is_OpenBSD
                m_util.is_FreeBSD.return_value = is_FreeBSD
                m_util.is_OpenBSD.return_value = is_OpenBSD
                cc_ntp.handle("notimportant", cfg, mycloud, None)
                m_subp.assert_called_with(
                    expected_service_call, capture=True, rcs=None
                )

            self.assertEqual(expected_content, util.load_text_file(confpath))

    @mock.patch("cloudinit.util.system_info")
    def test_opensuse_picks_chrony(self, m_sysinfo):
        """Test opensuse picks chrony or ntp on certain distro versions"""
        #  < 15.0  => ntp
        m_sysinfo.return_value = {"dist": ("openSUSE", "13.2", "Harlequin")}
        mycloud = self._get_cloud("opensuse")
        expected_client = mycloud.distro.preferred_ntp_clients[0]
        self.assertEqual("ntp", expected_client)

        #  >= 15.0 and  not openSUSE => chrony
        m_sysinfo.return_value = {
            "dist": ("SLES", "15.0", "SUSE Linux Enterprise Server 15")
        }
        mycloud = self._get_cloud("sles")
        expected_client = mycloud.distro.preferred_ntp_clients[0]
        self.assertEqual("chrony", expected_client)

        #  >= 15.0 and  openSUSE and ver != 42  => chrony
        m_sysinfo.return_value = {
            "dist": ("openSUSE Tumbleweed", "20180326", "timbleweed")
        }
        mycloud = self._get_cloud("opensuse")
        expected_client = mycloud.distro.preferred_ntp_clients[0]
        self.assertEqual("chrony", expected_client)

    @mock.patch("cloudinit.config.cc_ntp.subp.which")
    def test_snappy_system_picks_timesyncd(self, m_which):
        """Test snappy systems prefer installed clients"""

        # we are on ubuntu-core here
        self.m_snappy.return_value = True

        # ubuntu core systems will have timesyncd installed, so simulate that.
        # First None is for the 'eatmydata' check when initializing apt
        # when initializing the distro class. The rest represent possible
        # finds the various npt services
        m_which.side_effect = iter(
            [None, None, "/lib/systemd/systemd-timesyncd", None, None, None]
        )
        distro = "ubuntu"
        mycloud = self._get_cloud(distro)
        distro_configs = cc_ntp.distro_ntp_client_configs(distro)
        expected_client = "systemd-timesyncd"
        expected_cfg = distro_configs[expected_client]
        expected_calls = []
        # we only get to timesyncd
        for client in mycloud.distro.preferred_ntp_clients[0:2]:
            cfg = distro_configs[client]
            expected_calls.append(mock.call(cfg["check_exe"]))
        result = cc_ntp.select_ntp_client(None, mycloud.distro)
        m_which.assert_has_calls(expected_calls)
        self.assertEqual(sorted(expected_cfg), sorted(cfg))
        self.assertEqual(sorted(expected_cfg), sorted(result))

    @mock.patch("cloudinit.config.cc_ntp.subp.which")
    def test_ntp_distro_searches_all_preferred_clients(self, m_which):
        """Test select_ntp_client search all distro perferred clients"""
        # nothing is installed
        m_which.return_value = None
        for distro in cc_ntp.distros:
            mycloud = self._get_cloud(distro)
            distro_configs = cc_ntp.distro_ntp_client_configs(distro)
            expected_client = mycloud.distro.preferred_ntp_clients[0]
            expected_cfg = distro_configs[expected_client]
            expected_calls = []
            for client in mycloud.distro.preferred_ntp_clients:
                cfg = distro_configs[client]
                expected_calls.append(mock.call(cfg["check_exe"]))
            cc_ntp.select_ntp_client({}, mycloud.distro)
            m_which.assert_has_calls(expected_calls)
            self.assertEqual(sorted(expected_cfg), sorted(cfg))

    @mock.patch("cloudinit.config.cc_ntp.subp.which")
    def test_user_cfg_ntp_client_auto_uses_distro_clients(self, m_which):
        """Test user_cfg.ntp_client='auto' defaults to distro search"""
        # nothing is installed
        m_which.return_value = None
        for distro in cc_ntp.distros:
            mycloud = self._get_cloud(distro)
            distro_configs = cc_ntp.distro_ntp_client_configs(distro)
            expected_client = mycloud.distro.preferred_ntp_clients[0]
            expected_cfg = distro_configs[expected_client]
            expected_calls = []
            for client in mycloud.distro.preferred_ntp_clients:
                cfg = distro_configs[client]
                expected_calls.append(mock.call(cfg["check_exe"]))
            cc_ntp.select_ntp_client("auto", mycloud.distro)
            m_which.assert_has_calls(expected_calls)
            self.assertEqual(sorted(expected_cfg), sorted(cfg))

    @mock.patch("cloudinit.config.cc_ntp.write_ntp_config_template")
    @mock.patch("cloudinit.cloud.Cloud.get_template_filename")
    @mock.patch("cloudinit.config.cc_ntp.subp.which")
    def test_ntp_custom_client_overrides_installed_clients(
        self, m_which, m_tmpfn, m_write
    ):
        """Test user client is installed despite other clients present"""
        client = "ntpdate"
        cfg = {"ntp": {"ntp_client": client}}
        for distro in cc_ntp.distros:
            # client is not installed
            m_which.return_value = None
            mycloud = self._get_cloud(distro)
            with mock.patch.object(
                mycloud.distro, "install_packages"
            ) as m_install:
                cc_ntp.handle("notimportant", cfg, mycloud, None)
            m_install.assert_called_with([client])
            m_which.assert_called_with(client)

    @mock.patch("cloudinit.config.cc_ntp.subp.which")
    def test_ntp_system_config_overrides_distro_builtin_clients(self, m_which):
        """Test distro system_config overrides builtin preferred ntp clients"""
        system_client = "chrony"
        sys_cfg = {"ntp_client": system_client}
        # no clients installed
        m_which.return_value = None
        for distro in cc_ntp.distros:
            mycloud = self._get_cloud(distro, sys_cfg=sys_cfg)
            distro_configs = cc_ntp.distro_ntp_client_configs(distro)
            expected_cfg = distro_configs[system_client]
            result = cc_ntp.select_ntp_client(None, mycloud.distro)
            self.assertEqual(sorted(expected_cfg), sorted(result))
            m_which.assert_has_calls([])

    @mock.patch("cloudinit.config.cc_ntp.subp.which")
    def test_ntp_user_config_overrides_system_cfg(self, m_which):
        """Test user-data overrides system_config ntp_client"""
        system_client = "chrony"
        sys_cfg = {"ntp_client": system_client}
        user_client = "systemd-timesyncd"
        # no clients installed
        m_which.return_value = None
        for distro in cc_ntp.distros:
            mycloud = self._get_cloud(distro, sys_cfg=sys_cfg)
            distro_configs = cc_ntp.distro_ntp_client_configs(distro)
            expected_cfg = distro_configs[user_client]
            result = cc_ntp.select_ntp_client(user_client, mycloud.distro)
            self.assertEqual(sorted(expected_cfg), sorted(result))
            m_which.assert_has_calls([])

    @mock.patch("cloudinit.config.cc_ntp.install_ntp_client")
    def test_ntp_user_provided_config_with_template(self, m_install):
        custom = r"\n#MyCustomTemplate"
        user_template = NTP_TEMPLATE + custom
        confpath = os.path.join(self.new_root, "etc/myntp/myntp.conf")
        cfg = {
            "ntp": {
                "pools": ["mypool.org"],
                "ntp_client": "myntpd",
                "config": {
                    "check_exe": "myntpd",
                    "confpath": confpath,
                    "packages": ["myntp"],
                    "service_name": "myntp",
                    "template": user_template,
                },
            }
        }
        for distro in cc_ntp.distros:
            mycloud = self._get_cloud(distro)
            mock_path = "cloudinit.config.cc_ntp.temp_utils.get_tmp_ancestor"
            with mock.patch(mock_path, lambda *_: self.new_root):
                cc_ntp.handle("notimportant", cfg, mycloud, None)
            self.assertEqual(
                "servers []\npools ['mypool.org']\n%s" % custom,
                util.load_text_file(confpath),
            )

    @mock.patch("cloudinit.config.cc_ntp.supplemental_schema_validation")
    @mock.patch("cloudinit.config.cc_ntp.install_ntp_client")
    @mock.patch("cloudinit.config.cc_ntp.select_ntp_client")
    def test_ntp_user_provided_config_template_only(
        self, m_select, m_install, m_schema
    ):
        """Test custom template for default client"""
        custom = r"\n#MyCustomTemplate"
        user_template = NTP_TEMPLATE + custom
        client = "chrony"
        cfg = {
            "pools": ["mypool.org"],
            "ntp_client": client,
            "config": {
                "template": user_template,
            },
        }
        expected_merged_cfg = {
            "check_exe": "chronyd",
            "confpath": "{tmpdir}/client.conf".format(tmpdir=self.new_root),
            "template_name": "client.conf",
            "template": user_template,
            "service_name": "chrony",
            "packages": ["chrony"],
        }
        for distro in cc_ntp.distros:
            mycloud = self._get_cloud(distro)
            ntpconfig = self._mock_ntp_client_config(
                client=client, distro=distro
            )
            confpath = ntpconfig["confpath"]
            m_select.return_value = ntpconfig
            mock_path = "cloudinit.config.cc_ntp.temp_utils.get_tmp_ancestor"
            with mock.patch(mock_path, lambda *_: self.new_root):
                cc_ntp.handle("notimportant", {"ntp": cfg}, mycloud, None)
            self.assertEqual(
                "servers []\npools ['mypool.org']\n%s" % custom,
                util.load_text_file(confpath),
            )
        m_schema.assert_called_with(expected_merged_cfg)


class TestSupplementalSchemaValidation(CiTestCase):
    def test_error_on_missing_keys(self):
        """ValueError raised reporting any missing required ntp:config keys"""
        cfg = {}
        match = (
            r"Invalid ntp configuration:\\nMissing required ntp:config"
            " keys: check_exe, confpath, packages, service_name"
        )
        with self.assertRaisesRegex(ValueError, match):
            cc_ntp.supplemental_schema_validation(cfg)

    def test_error_requiring_either_template_or_template_name(self):
        """ValueError raised if both template not template_name are None."""
        cfg = {
            "confpath": "someconf",
            "check_exe": "",
            "service_name": "",
            "template": None,
            "template_name": None,
            "packages": [],
        }
        match = (
            r"Invalid ntp configuration:\\nEither ntp:config:template"
            " or ntp:config:template_name values are required"
        )
        with self.assertRaisesRegex(ValueError, match):
            cc_ntp.supplemental_schema_validation(cfg)

    def test_error_on_non_list_values(self):
        """ValueError raised when packages is not of type list."""
        cfg = {
            "confpath": "someconf",
            "check_exe": "",
            "service_name": "",
            "template": "asdf",
            "template_name": None,
            "packages": "NOPE",
        }
        match = (
            r"Invalid ntp configuration:\\nExpected a list of required"
            " package names for ntp:config:packages. Found \\(NOPE\\)"
        )
        with self.assertRaisesRegex(ValueError, match):
            cc_ntp.supplemental_schema_validation(cfg)

    def test_error_on_non_string_values(self):
        """ValueError raised for any values expected as string type."""
        cfg = {
            "confpath": 1,
            "check_exe": 2,
            "service_name": 3,
            "template": 4,
            "template_name": 5,
            "packages": [],
        }
        errors = [
            "Expected a config file path ntp:config:confpath. Found (1)",
            "Expected a string type for ntp:config:check_exe. Found (2)",
            "Expected a string type for ntp:config:service_name. Found (3)",
            "Expected a string type for ntp:config:template. Found (4)",
            "Expected a string type for ntp:config:template_name. Found (5)",
        ]
        with self.assertRaises(ValueError) as context_mgr:
            cc_ntp.supplemental_schema_validation(cfg)
        error_msg = str(context_mgr.exception)
        for error in errors:
            self.assertIn(error, error_msg)


class TestNTPSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Allow empty ntp config
            ({"ntp": None}, None),
            (
                {
                    "ntp": {
                        "invalidkey": 1,
                        "pools": ["0.mycompany.pool.ntp.org"],
                    }
                },
                re.escape(
                    "ntp: Additional properties are not allowed ('invalidkey'"
                ),
            ),
            (
                {
                    "ntp": {
                        "pools": ["0.mypool.org", "0.mypool.org"],
                        "servers": ["10.0.0.1", "10.0.0.1"],
                    }
                },
                re.escape(
                    "ntp.pools: ['0.mypool.org', '0.mypool.org'] has"
                    " non-unique elements"
                ),
            ),
            (
                {
                    "ntp": {
                        "pools": [123],
                        "servers": ["www.example.com", None],
                    }
                },
                "ntp.pools.0: 123 is not of type 'string'.*"
                "ntp.servers.1: None is not of type 'string'",
            ),
            (
                {"ntp": {"pools": 123, "servers": "non-array"}},
                "ntp.pools: 123 is not of type 'array'.*"
                "ntp.servers: 'non-array' is not of type 'array'",
            ),
            (
                {
                    "ntp": {
                        "peers": [123],
                        "allow": ["www.example.com", None],
                    }
                },
                "Cloud config schema errors: "
                "ntp.allow.1: None is not of type 'string',*"
                ", ntp.peers.0: 123 is not of type 'string'",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
