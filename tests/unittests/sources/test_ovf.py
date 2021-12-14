# Copyright (C) 2016 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import os
from collections import OrderedDict
from textwrap import dedent

from cloudinit import subp, util
from cloudinit.helpers import Paths
from cloudinit.safeyaml import YAMLError
from cloudinit.sources import DataSourceOVF as dsovf
from cloudinit.sources.helpers.vmware.imc.config_custom_script import (
    CustomScriptNotFound,
)
from tests.unittests.helpers import CiTestCase, mock, wrap_and_call

MPATH = "cloudinit.sources.DataSourceOVF."

NOT_FOUND = None

OVF_ENV_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<Environment xmlns="http://schemas.dmtf.org/ovf/environment/1"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:oe="http://schemas.dmtf.org/ovf/environment/1"
  xsi:schemaLocation="http://schemas.dmtf.org/ovf/environment/1 ../dsp8027.xsd"
  oe:id="WebTier">
  <!-- Information about hypervisor platform -->
  <oe:PlatformSection>
      <Kind>ESX Server</Kind>
      <Version>3.0.1</Version>
      <Vendor>VMware, Inc.</Vendor>
      <Locale>en_US</Locale>
  </oe:PlatformSection>
  <!--- Properties defined for this virtual machine -->
  <PropertySection>
{properties}
  </PropertySection>
</Environment>
"""


def fill_properties(props, template=OVF_ENV_CONTENT):
    lines = []
    prop_tmpl = '<Property oe:key="{key}" oe:value="{val}"/>'
    for key, val in props.items():
        lines.append(prop_tmpl.format(key=key, val=val))
    indent = "        "
    properties = "".join([indent + line + "\n" for line in lines])
    return template.format(properties=properties)


class TestReadOvfEnv(CiTestCase):
    def test_with_b64_userdata(self):
        user_data = "#!/bin/sh\necho hello world\n"
        user_data_b64 = base64.b64encode(user_data.encode()).decode()
        props = {
            "user-data": user_data_b64,
            "password": "passw0rd",
            "instance-id": "inst-001",
        }
        env = fill_properties(props)
        md, ud, cfg = dsovf.read_ovf_environment(env)
        self.assertEqual({"instance-id": "inst-001"}, md)
        self.assertEqual(user_data.encode(), ud)
        self.assertEqual({"password": "passw0rd"}, cfg)

    def test_with_non_b64_userdata(self):
        user_data = "my-user-data"
        props = {"user-data": user_data, "instance-id": "inst-001"}
        env = fill_properties(props)
        md, ud, cfg = dsovf.read_ovf_environment(env)
        self.assertEqual({"instance-id": "inst-001"}, md)
        self.assertEqual(user_data.encode(), ud)
        self.assertEqual({}, cfg)

    def test_with_no_userdata(self):
        props = {"password": "passw0rd", "instance-id": "inst-001"}
        env = fill_properties(props)
        md, ud, cfg = dsovf.read_ovf_environment(env)
        self.assertEqual({"instance-id": "inst-001"}, md)
        self.assertEqual({"password": "passw0rd"}, cfg)
        self.assertIsNone(ud)

    def test_with_b64_network_config_enable_read_network(self):
        network_config = dedent(
            """\
        network:
           version: 2
           ethernets:
              nics:
                 nameservers:
                    addresses:
                    - 127.0.0.53
                    search:
                    - eng.vmware.com
                    - vmware.com
                 match:
                    name: eth*
                 gateway4: 10.10.10.253
                 dhcp4: false
                 addresses:
                 - 10.10.10.1/24
        """
        )
        network_config_b64 = base64.b64encode(network_config.encode()).decode()
        props = {
            "network-config": network_config_b64,
            "password": "passw0rd",
            "instance-id": "inst-001",
        }
        env = fill_properties(props)
        md, ud, cfg = dsovf.read_ovf_environment(env, True)
        self.assertEqual("inst-001", md["instance-id"])
        self.assertEqual({"password": "passw0rd"}, cfg)
        self.assertEqual(
            {
                "version": 2,
                "ethernets": {
                    "nics": {
                        "nameservers": {
                            "addresses": ["127.0.0.53"],
                            "search": ["eng.vmware.com", "vmware.com"],
                        },
                        "match": {"name": "eth*"},
                        "gateway4": "10.10.10.253",
                        "dhcp4": False,
                        "addresses": ["10.10.10.1/24"],
                    }
                },
            },
            md["network-config"],
        )
        self.assertIsNone(ud)

    def test_with_non_b64_network_config_enable_read_network(self):
        network_config = dedent(
            """\
        network:
           version: 2
           ethernets:
              nics:
                 nameservers:
                    addresses:
                    - 127.0.0.53
                    search:
                    - eng.vmware.com
                    - vmware.com
                 match:
                    name: eth*
                 gateway4: 10.10.10.253
                 dhcp4: false
                 addresses:
                 - 10.10.10.1/24
        """
        )
        props = {
            "network-config": network_config,
            "password": "passw0rd",
            "instance-id": "inst-001",
        }
        env = fill_properties(props)
        md, ud, cfg = dsovf.read_ovf_environment(env, True)
        self.assertEqual({"instance-id": "inst-001"}, md)
        self.assertEqual({"password": "passw0rd"}, cfg)
        self.assertIsNone(ud)

    def test_with_b64_network_config_disable_read_network(self):
        network_config = dedent(
            """\
        network:
           version: 2
           ethernets:
              nics:
                 nameservers:
                    addresses:
                    - 127.0.0.53
                    search:
                    - eng.vmware.com
                    - vmware.com
                 match:
                    name: eth*
                 gateway4: 10.10.10.253
                 dhcp4: false
                 addresses:
                 - 10.10.10.1/24
        """
        )
        network_config_b64 = base64.b64encode(network_config.encode()).decode()
        props = {
            "network-config": network_config_b64,
            "password": "passw0rd",
            "instance-id": "inst-001",
        }
        env = fill_properties(props)
        md, ud, cfg = dsovf.read_ovf_environment(env)
        self.assertEqual({"instance-id": "inst-001"}, md)
        self.assertEqual({"password": "passw0rd"}, cfg)
        self.assertIsNone(ud)


class TestMarkerFiles(CiTestCase):
    def setUp(self):
        super(TestMarkerFiles, self).setUp()
        self.tdir = self.tmp_dir()

    def test_false_when_markerid_none(self):
        """Return False when markerid provided is None."""
        self.assertFalse(
            dsovf.check_marker_exists(markerid=None, marker_dir=self.tdir)
        )

    def test_markerid_file_exist(self):
        """Return False when markerid file path does not exist,
        True otherwise."""
        self.assertFalse(dsovf.check_marker_exists("123", self.tdir))

        marker_file = self.tmp_path(".markerfile-123.txt", self.tdir)
        util.write_file(marker_file, "")
        self.assertTrue(dsovf.check_marker_exists("123", self.tdir))

    def test_marker_file_setup(self):
        """Test creation of marker files."""
        markerfilepath = self.tmp_path(".markerfile-hi.txt", self.tdir)
        self.assertFalse(os.path.exists(markerfilepath))
        dsovf.setup_marker_files(markerid="hi", marker_dir=self.tdir)
        self.assertTrue(os.path.exists(markerfilepath))


class TestDatasourceOVF(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestDatasourceOVF, self).setUp()
        self.datasource = dsovf.DataSourceOVF
        self.tdir = self.tmp_dir()

    def test_get_data_false_on_none_dmi_data(self):
        """When dmi for system-product-name is None, get_data returns False."""
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(sys_cfg={}, distro={}, paths=paths)
        retcode = wrap_and_call(
            "cloudinit.sources.DataSourceOVF",
            {
                "dmi.read_dmi_data": None,
                "transport_iso9660": NOT_FOUND,
                "transport_vmware_guestinfo": NOT_FOUND,
            },
            ds.get_data,
        )
        self.assertFalse(retcode, "Expected False return from ds.get_data")
        self.assertIn(
            "DEBUG: No system-product-name found", self.logs.getvalue()
        )

    def test_get_data_vmware_customization_disabled(self):
        """When vmware customization is disabled via sys_cfg and
        allow_raw_data is disabled via ds_cfg, log a message.
        """
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={
                "disable_vmware_customization": True,
                "datasource": {"OVF": {"allow_raw_data": False}},
            },
            distro={},
            paths=paths,
        )
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [MISC]
            MARKER-ID = 12345345
            """
        )
        util.write_file(conf_file, conf_content)
        retcode = wrap_and_call(
            "cloudinit.sources.DataSourceOVF",
            {
                "dmi.read_dmi_data": "vmware",
                "transport_iso9660": NOT_FOUND,
                "transport_vmware_guestinfo": NOT_FOUND,
                "util.del_dir": True,
                "search_file": self.tdir,
                "wait_for_imc_cfg_file": conf_file,
            },
            ds.get_data,
        )
        self.assertFalse(retcode, "Expected False return from ds.get_data")
        self.assertIn(
            "DEBUG: Customization for VMware platform is disabled.",
            self.logs.getvalue(),
        )

    def test_get_data_vmware_customization_sys_cfg_disabled(self):
        """When vmware customization is disabled via sys_cfg and
        no meta data is found, log a message.
        """
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={
                "disable_vmware_customization": True,
                "datasource": {"OVF": {"allow_raw_data": True}},
            },
            distro={},
            paths=paths,
        )
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [MISC]
            MARKER-ID = 12345345
            """
        )
        util.write_file(conf_file, conf_content)
        retcode = wrap_and_call(
            "cloudinit.sources.DataSourceOVF",
            {
                "dmi.read_dmi_data": "vmware",
                "transport_iso9660": NOT_FOUND,
                "transport_vmware_guestinfo": NOT_FOUND,
                "util.del_dir": True,
                "search_file": self.tdir,
                "wait_for_imc_cfg_file": conf_file,
            },
            ds.get_data,
        )
        self.assertFalse(retcode, "Expected False return from ds.get_data")
        self.assertIn(
            "DEBUG: Customization using VMware config is disabled.",
            self.logs.getvalue(),
        )

    def test_get_data_allow_raw_data_disabled(self):
        """When allow_raw_data is disabled via ds_cfg and
        meta data is found, log a message.
        """
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={
                "disable_vmware_customization": False,
                "datasource": {"OVF": {"allow_raw_data": False}},
            },
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        util.write_file(metadata_file, "This is meta data")
        retcode = wrap_and_call(
            "cloudinit.sources.DataSourceOVF",
            {
                "dmi.read_dmi_data": "vmware",
                "transport_iso9660": NOT_FOUND,
                "transport_vmware_guestinfo": NOT_FOUND,
                "util.del_dir": True,
                "search_file": self.tdir,
                "wait_for_imc_cfg_file": conf_file,
                "collect_imc_file_paths": [self.tdir + "/test-meta", "", ""],
            },
            ds.get_data,
        )
        self.assertFalse(retcode, "Expected False return from ds.get_data")
        self.assertIn(
            "DEBUG: Customization using raw data is disabled.",
            self.logs.getvalue(),
        )

    def test_get_data_vmware_customization_enabled(self):
        """When cloud-init workflow for vmware is enabled via sys_cfg log a
        message.
        """
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CUSTOM-SCRIPT]
            SCRIPT-NAME = test-script
            [MISC]
            MARKER-ID = 12345345
            """
        )
        util.write_file(conf_file, conf_content)
        with mock.patch(MPATH + "get_tools_config", return_value="true"):
            with self.assertRaises(CustomScriptNotFound) as context:
                wrap_and_call(
                    "cloudinit.sources.DataSourceOVF",
                    {
                        "dmi.read_dmi_data": "vmware",
                        "util.del_dir": True,
                        "search_file": self.tdir,
                        "wait_for_imc_cfg_file": conf_file,
                        "get_nics_to_enable": "",
                    },
                    ds.get_data,
                )
        customscript = self.tmp_path("test-script", self.tdir)
        self.assertIn(
            "Script %s not found!!" % customscript, str(context.exception)
        )

    def test_get_data_cust_script_disabled(self):
        """If custom script is disabled by VMware tools configuration,
        raise a RuntimeError.
        """
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CUSTOM-SCRIPT]
            SCRIPT-NAME = test-script
            [MISC]
            MARKER-ID = 12345346
            """
        )
        util.write_file(conf_file, conf_content)
        # Prepare the custom sript
        customscript = self.tmp_path("test-script", self.tdir)
        util.write_file(customscript, "This is the post cust script")

        with mock.patch(MPATH + "get_tools_config", return_value="invalid"):
            with mock.patch(
                MPATH + "set_customization_status", return_value=("msg", b"")
            ):
                with self.assertRaises(RuntimeError) as context:
                    wrap_and_call(
                        "cloudinit.sources.DataSourceOVF",
                        {
                            "dmi.read_dmi_data": "vmware",
                            "util.del_dir": True,
                            "search_file": self.tdir,
                            "wait_for_imc_cfg_file": conf_file,
                            "get_nics_to_enable": "",
                        },
                        ds.get_data,
                    )
        self.assertIn(
            "Custom script is disabled by VM Administrator",
            str(context.exception),
        )

    def test_get_data_cust_script_enabled(self):
        """If custom script is enabled by VMware tools configuration,
        execute the script.
        """
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CUSTOM-SCRIPT]
            SCRIPT-NAME = test-script
            [MISC]
            MARKER-ID = 12345346
            """
        )
        util.write_file(conf_file, conf_content)

        # Mock custom script is enabled by return true when calling
        # get_tools_config
        with mock.patch(MPATH + "get_tools_config", return_value="true"):
            with mock.patch(
                MPATH + "set_customization_status", return_value=("msg", b"")
            ):
                with self.assertRaises(CustomScriptNotFound) as context:
                    wrap_and_call(
                        "cloudinit.sources.DataSourceOVF",
                        {
                            "dmi.read_dmi_data": "vmware",
                            "util.del_dir": True,
                            "search_file": self.tdir,
                            "wait_for_imc_cfg_file": conf_file,
                            "get_nics_to_enable": "",
                        },
                        ds.get_data,
                    )
        # Verify custom script is trying to be executed
        customscript = self.tmp_path("test-script", self.tdir)
        self.assertIn(
            "Script %s not found!!" % customscript, str(context.exception)
        )

    def test_get_data_force_run_post_script_is_yes(self):
        """If DEFAULT-RUN-POST-CUST-SCRIPT is yes, custom script could run if
        enable-custom-scripts is not defined in VM Tools configuration
        """
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        # set DEFAULT-RUN-POST-CUST-SCRIPT = yes so that enable-custom-scripts
        # default value is TRUE
        conf_content = dedent(
            """\
            [CUSTOM-SCRIPT]
            SCRIPT-NAME = test-script
            [MISC]
            MARKER-ID = 12345346
            DEFAULT-RUN-POST-CUST-SCRIPT = yes
            """
        )
        util.write_file(conf_file, conf_content)

        # Mock get_tools_config(section, key, defaultVal) to return
        # defaultVal
        def my_get_tools_config(*args, **kwargs):
            return args[2]

        with mock.patch(
            MPATH + "get_tools_config", side_effect=my_get_tools_config
        ):
            with mock.patch(
                MPATH + "set_customization_status", return_value=("msg", b"")
            ):
                with self.assertRaises(CustomScriptNotFound) as context:
                    wrap_and_call(
                        "cloudinit.sources.DataSourceOVF",
                        {
                            "dmi.read_dmi_data": "vmware",
                            "util.del_dir": True,
                            "search_file": self.tdir,
                            "wait_for_imc_cfg_file": conf_file,
                            "get_nics_to_enable": "",
                        },
                        ds.get_data,
                    )
        # Verify custom script still runs although it is
        # disabled by VMware Tools
        customscript = self.tmp_path("test-script", self.tdir)
        self.assertIn(
            "Script %s not found!!" % customscript, str(context.exception)
        )

    def test_get_data_non_vmware_seed_platform_info(self):
        """Platform info properly reports when on non-vmware platforms."""
        paths = Paths({"cloud_dir": self.tdir, "run_dir": self.tdir})
        # Write ovf-env.xml seed file
        seed_dir = self.tmp_path("seed", dir=self.tdir)
        ovf_env = self.tmp_path("ovf-env.xml", dir=seed_dir)
        util.write_file(ovf_env, OVF_ENV_CONTENT)
        ds = self.datasource(sys_cfg={}, distro={}, paths=paths)

        self.assertEqual("ovf", ds.cloud_name)
        self.assertEqual("ovf", ds.platform_type)
        with mock.patch(MPATH + "dmi.read_dmi_data", return_value="!VMware"):
            with mock.patch(MPATH + "transport_vmware_guestinfo") as m_guestd:
                with mock.patch(MPATH + "transport_iso9660") as m_iso9660:
                    m_iso9660.return_value = NOT_FOUND
                    m_guestd.return_value = NOT_FOUND
                    self.assertTrue(ds.get_data())
                    self.assertEqual(
                        "ovf (%s/seed/ovf-env.xml)" % self.tdir, ds.subplatform
                    )

    def test_get_data_vmware_seed_platform_info(self):
        """Platform info properly reports when on VMware platform."""
        paths = Paths({"cloud_dir": self.tdir, "run_dir": self.tdir})
        # Write ovf-env.xml seed file
        seed_dir = self.tmp_path("seed", dir=self.tdir)
        ovf_env = self.tmp_path("ovf-env.xml", dir=seed_dir)
        util.write_file(ovf_env, OVF_ENV_CONTENT)
        ds = self.datasource(sys_cfg={}, distro={}, paths=paths)

        self.assertEqual("ovf", ds.cloud_name)
        self.assertEqual("ovf", ds.platform_type)
        with mock.patch(MPATH + "dmi.read_dmi_data", return_value="VMWare"):
            with mock.patch(MPATH + "transport_vmware_guestinfo") as m_guestd:
                with mock.patch(MPATH + "transport_iso9660") as m_iso9660:
                    m_iso9660.return_value = NOT_FOUND
                    m_guestd.return_value = NOT_FOUND
                    self.assertTrue(ds.get_data())
                    self.assertEqual(
                        "vmware (%s/seed/ovf-env.xml)" % self.tdir,
                        ds.subplatform,
                    )

    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.sources.DataSource.persist_instance_data")
    def test_get_data_vmware_guestinfo_with_network_config(
        self, m_persist, m_subp
    ):
        self._test_get_data_with_network_config(guestinfo=False, iso=True)

    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.sources.DataSource.persist_instance_data")
    def test_get_data_iso9660_with_network_config(self, m_persist, m_subp):
        self._test_get_data_with_network_config(guestinfo=True, iso=False)

    def _test_get_data_with_network_config(self, guestinfo, iso):
        network_config = dedent(
            """\
        network:
           version: 2
           ethernets:
              nics:
                 nameservers:
                    addresses:
                    - 127.0.0.53
                    search:
                    - vmware.com
                 match:
                    name: eth*
                 gateway4: 10.10.10.253
                 dhcp4: false
                 addresses:
                 - 10.10.10.1/24
        """
        )
        network_config_b64 = base64.b64encode(network_config.encode()).decode()
        props = {
            "network-config": network_config_b64,
            "password": "passw0rd",
            "instance-id": "inst-001",
        }
        env = fill_properties(props)
        paths = Paths({"cloud_dir": self.tdir, "run_dir": self.tdir})
        ds = self.datasource(sys_cfg={}, distro={}, paths=paths)
        with mock.patch(
            MPATH + "transport_vmware_guestinfo",
            return_value=env if guestinfo else NOT_FOUND,
        ):
            with mock.patch(
                MPATH + "transport_iso9660",
                return_value=env if iso else NOT_FOUND,
            ):
                self.assertTrue(ds.get_data())
                self.assertEqual("inst-001", ds.metadata["instance-id"])
                self.assertEqual(
                    {
                        "version": 2,
                        "ethernets": {
                            "nics": {
                                "nameservers": {
                                    "addresses": ["127.0.0.53"],
                                    "search": ["vmware.com"],
                                },
                                "match": {"name": "eth*"},
                                "gateway4": "10.10.10.253",
                                "dhcp4": False,
                                "addresses": ["10.10.10.1/24"],
                            }
                        },
                    },
                    ds.network_config,
                )

    def test_get_data_cloudinit_metadata_json(self):
        """Test metadata can be loaded to cloud-init metadata and network.
        The metadata format is json.
        """
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        metadata_content = dedent(
            """\
            {
              "instance-id": "cloud-vm",
              "local-hostname": "my-host.domain.com",
              "network": {
                "version": 2,
                "ethernets": {
                  "eths": {
                    "match": {
                      "name": "ens*"
                    },
                    "dhcp4": true
                  }
                }
              }
            }
            """
        )
        util.write_file(metadata_file, metadata_content)

        with mock.patch(
            MPATH + "set_customization_status", return_value=("msg", b"")
        ):
            result = wrap_and_call(
                "cloudinit.sources.DataSourceOVF",
                {
                    "dmi.read_dmi_data": "vmware",
                    "util.del_dir": True,
                    "search_file": self.tdir,
                    "wait_for_imc_cfg_file": conf_file,
                    "collect_imc_file_paths": [
                        self.tdir + "/test-meta",
                        "",
                        "",
                    ],
                    "get_nics_to_enable": "",
                },
                ds._get_data,
            )

        self.assertTrue(result)
        self.assertEqual("cloud-vm", ds.metadata["instance-id"])
        self.assertEqual("my-host.domain.com", ds.metadata["local-hostname"])
        self.assertEqual(2, ds.network_config["version"])
        self.assertTrue(ds.network_config["ethernets"]["eths"]["dhcp4"])

    def test_get_data_cloudinit_metadata_yaml(self):
        """Test metadata can be loaded to cloud-init metadata and network.
        The metadata format is yaml.
        """
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        metadata_content = dedent(
            """\
            instance-id: cloud-vm
            local-hostname: my-host.domain.com
            network:
                version: 2
                ethernets:
                    nics:
                        match:
                            name: ens*
                        dhcp4: yes
            """
        )
        util.write_file(metadata_file, metadata_content)

        with mock.patch(
            MPATH + "set_customization_status", return_value=("msg", b"")
        ):
            result = wrap_and_call(
                "cloudinit.sources.DataSourceOVF",
                {
                    "dmi.read_dmi_data": "vmware",
                    "util.del_dir": True,
                    "search_file": self.tdir,
                    "wait_for_imc_cfg_file": conf_file,
                    "collect_imc_file_paths": [
                        self.tdir + "/test-meta",
                        "",
                        "",
                    ],
                    "get_nics_to_enable": "",
                },
                ds._get_data,
            )

        self.assertTrue(result)
        self.assertEqual("cloud-vm", ds.metadata["instance-id"])
        self.assertEqual("my-host.domain.com", ds.metadata["local-hostname"])
        self.assertEqual(2, ds.network_config["version"])
        self.assertTrue(ds.network_config["ethernets"]["nics"]["dhcp4"])

    def test_get_data_cloudinit_metadata_not_valid(self):
        """Test metadata is not JSON or YAML format."""
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)

        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        metadata_content = "[This is not json or yaml format]a=b"
        util.write_file(metadata_file, metadata_content)

        with mock.patch(
            MPATH + "set_customization_status", return_value=("msg", b"")
        ):
            with self.assertRaises(YAMLError) as context:
                wrap_and_call(
                    "cloudinit.sources.DataSourceOVF",
                    {
                        "dmi.read_dmi_data": "vmware",
                        "util.del_dir": True,
                        "search_file": self.tdir,
                        "wait_for_imc_cfg_file": conf_file,
                        "collect_imc_file_paths": [
                            self.tdir + "/test-meta",
                            "",
                            "",
                        ],
                        "get_nics_to_enable": "",
                    },
                    ds.get_data,
                )

        self.assertIn(
            "expected '<document start>', but found '<scalar>'",
            str(context.exception),
        )

    def test_get_data_cloudinit_metadata_not_found(self):
        """Test metadata file can't be found."""
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )
        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            """
        )
        util.write_file(conf_file, conf_content)
        # Don't prepare the meta data file

        with mock.patch(
            MPATH + "set_customization_status", return_value=("msg", b"")
        ):
            with self.assertRaises(FileNotFoundError) as context:
                wrap_and_call(
                    "cloudinit.sources.DataSourceOVF",
                    {
                        "dmi.read_dmi_data": "vmware",
                        "util.del_dir": True,
                        "search_file": self.tdir,
                        "wait_for_imc_cfg_file": conf_file,
                        "get_nics_to_enable": "",
                    },
                    ds.get_data,
                )

        self.assertIn("is not found", str(context.exception))

    def test_get_data_cloudinit_userdata(self):
        """Test user data can be loaded to cloud-init user data."""
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": False},
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            USERDATA = test-user
            """
        )
        util.write_file(conf_file, conf_content)

        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        metadata_content = dedent(
            """\
            instance-id: cloud-vm
            local-hostname: my-host.domain.com
            network:
                version: 2
                ethernets:
                    nics:
                        match:
                            name: ens*
                        dhcp4: yes
            """
        )
        util.write_file(metadata_file, metadata_content)

        # Prepare the user data file
        userdata_file = self.tmp_path("test-user", self.tdir)
        userdata_content = "This is the user data"
        util.write_file(userdata_file, userdata_content)

        with mock.patch(
            MPATH + "set_customization_status", return_value=("msg", b"")
        ):
            result = wrap_and_call(
                "cloudinit.sources.DataSourceOVF",
                {
                    "dmi.read_dmi_data": "vmware",
                    "util.del_dir": True,
                    "search_file": self.tdir,
                    "wait_for_imc_cfg_file": conf_file,
                    "collect_imc_file_paths": [
                        self.tdir + "/test-meta",
                        self.tdir + "/test-user",
                        "",
                    ],
                    "get_nics_to_enable": "",
                },
                ds._get_data,
            )

        self.assertTrue(result)
        self.assertEqual("cloud-vm", ds.metadata["instance-id"])
        self.assertEqual(userdata_content, ds.userdata_raw)

    def test_get_data_cloudinit_userdata_not_found(self):
        """Test userdata file can't be found."""
        paths = Paths({"cloud_dir": self.tdir})
        ds = self.datasource(
            sys_cfg={"disable_vmware_customization": True},
            distro={},
            paths=paths,
        )

        # Prepare the conf file
        conf_file = self.tmp_path("test-cust", self.tdir)
        conf_content = dedent(
            """\
            [CLOUDINIT]
            METADATA = test-meta
            USERDATA = test-user
            """
        )
        util.write_file(conf_file, conf_content)

        # Prepare the meta data file
        metadata_file = self.tmp_path("test-meta", self.tdir)
        metadata_content = dedent(
            """\
            instance-id: cloud-vm
            local-hostname: my-host.domain.com
            network:
                version: 2
                ethernets:
                    nics:
                        match:
                            name: ens*
                        dhcp4: yes
            """
        )
        util.write_file(metadata_file, metadata_content)

        # Don't prepare the user data file

        with mock.patch(
            MPATH + "set_customization_status", return_value=("msg", b"")
        ):
            with self.assertRaises(FileNotFoundError) as context:
                wrap_and_call(
                    "cloudinit.sources.DataSourceOVF",
                    {
                        "dmi.read_dmi_data": "vmware",
                        "util.del_dir": True,
                        "search_file": self.tdir,
                        "wait_for_imc_cfg_file": conf_file,
                        "get_nics_to_enable": "",
                    },
                    ds.get_data,
                )

        self.assertIn("is not found", str(context.exception))


class TestTransportIso9660(CiTestCase):
    def setUp(self):
        super(TestTransportIso9660, self).setUp()
        self.add_patch("cloudinit.util.find_devs_with", "m_find_devs_with")
        self.add_patch("cloudinit.util.mounts", "m_mounts")
        self.add_patch("cloudinit.util.mount_cb", "m_mount_cb")
        self.add_patch(
            "cloudinit.sources.DataSourceOVF.get_ovf_env", "m_get_ovf_env"
        )
        self.m_get_ovf_env.return_value = ("myfile", "mycontent")

    def test_find_already_mounted(self):
        """Check we call get_ovf_env from on matching mounted devices"""
        mounts = {
            "/dev/sr9": {
                "fstype": "iso9660",
                "mountpoint": "wark/media/sr9",
                "opts": "ro",
            }
        }
        self.m_mounts.return_value = mounts

        self.assertEqual("mycontent", dsovf.transport_iso9660())

    def test_find_already_mounted_skips_non_iso9660(self):
        """Check we call get_ovf_env ignoring non iso9660"""
        mounts = {
            "/dev/xvdb": {
                "fstype": "vfat",
                "mountpoint": "wark/foobar",
                "opts": "defaults,noatime",
            },
            "/dev/xvdc": {
                "fstype": "iso9660",
                "mountpoint": "wark/media/sr9",
                "opts": "ro",
            },
        }
        # We use an OrderedDict here to ensure we check xvdb before xvdc
        # as we're not mocking the regex matching, however, if we place
        # an entry in the results then we can be reasonably sure that
        # we're skipping an entry which fails to match.
        self.m_mounts.return_value = OrderedDict(
            sorted(mounts.items(), key=lambda t: t[0])
        )

        self.assertEqual("mycontent", dsovf.transport_iso9660())

    def test_find_already_mounted_matches_kname(self):
        """Check we dont regex match on basename of the device"""
        mounts = {
            "/dev/foo/bar/xvdc": {
                "fstype": "iso9660",
                "mountpoint": "wark/media/sr9",
                "opts": "ro",
            }
        }
        # we're skipping an entry which fails to match.
        self.m_mounts.return_value = mounts

        self.assertEqual(NOT_FOUND, dsovf.transport_iso9660())

    def test_mount_cb_called_on_blkdevs_with_iso9660(self):
        """Check we call mount_cb on blockdevs with iso9660 only"""
        self.m_mounts.return_value = {}
        self.m_find_devs_with.return_value = ["/dev/sr0"]
        self.m_mount_cb.return_value = ("myfile", "mycontent")

        self.assertEqual("mycontent", dsovf.transport_iso9660())
        self.m_mount_cb.assert_called_with(
            "/dev/sr0", dsovf.get_ovf_env, mtype="iso9660"
        )

    def test_mount_cb_called_on_blkdevs_with_iso9660_check_regex(self):
        """Check we call mount_cb on blockdevs with iso9660 and match regex"""
        self.m_mounts.return_value = {}
        self.m_find_devs_with.return_value = [
            "/dev/abc",
            "/dev/my-cdrom",
            "/dev/sr0",
        ]
        self.m_mount_cb.return_value = ("myfile", "mycontent")

        self.assertEqual("mycontent", dsovf.transport_iso9660())
        self.m_mount_cb.assert_called_with(
            "/dev/sr0", dsovf.get_ovf_env, mtype="iso9660"
        )

    def test_mount_cb_not_called_no_matches(self):
        """Check we don't call mount_cb if nothing matches"""
        self.m_mounts.return_value = {}
        self.m_find_devs_with.return_value = ["/dev/vg/myovf"]

        self.assertEqual(NOT_FOUND, dsovf.transport_iso9660())
        self.assertEqual(0, self.m_mount_cb.call_count)

    def test_mount_cb_called_require_iso_false(self):
        """Check we call mount_cb on blockdevs with require_iso=False"""
        self.m_mounts.return_value = {}
        self.m_find_devs_with.return_value = ["/dev/xvdz"]
        self.m_mount_cb.return_value = ("myfile", "mycontent")

        self.assertEqual(
            "mycontent", dsovf.transport_iso9660(require_iso=False)
        )

        self.m_mount_cb.assert_called_with(
            "/dev/xvdz", dsovf.get_ovf_env, mtype=None
        )

    def test_maybe_cdrom_device_none(self):
        """Test maybe_cdrom_device returns False for none/empty input"""
        self.assertFalse(dsovf.maybe_cdrom_device(None))
        self.assertFalse(dsovf.maybe_cdrom_device(""))

    def test_maybe_cdrom_device_non_string_exception(self):
        """Test maybe_cdrom_device raises ValueError on non-string types"""
        with self.assertRaises(ValueError):
            dsovf.maybe_cdrom_device({"a": "eleven"})

    def test_maybe_cdrom_device_false_on_multi_dir_paths(self):
        """Test maybe_cdrom_device is false on /dev[/.*]/* paths"""
        self.assertFalse(dsovf.maybe_cdrom_device("/dev/foo/sr0"))
        self.assertFalse(dsovf.maybe_cdrom_device("foo/sr0"))
        self.assertFalse(dsovf.maybe_cdrom_device("../foo/sr0"))
        self.assertFalse(dsovf.maybe_cdrom_device("../foo/sr0"))

    def test_maybe_cdrom_device_true_on_hd_partitions(self):
        """Test maybe_cdrom_device is false on /dev/hd[a-z][0-9]+ paths"""
        self.assertTrue(dsovf.maybe_cdrom_device("/dev/hda1"))
        self.assertTrue(dsovf.maybe_cdrom_device("hdz9"))

    def test_maybe_cdrom_device_true_on_valid_relative_paths(self):
        """Test maybe_cdrom_device normalizes paths"""
        self.assertTrue(dsovf.maybe_cdrom_device("/dev/wark/../sr9"))
        self.assertTrue(dsovf.maybe_cdrom_device("///sr0"))
        self.assertTrue(dsovf.maybe_cdrom_device("/sr0"))
        self.assertTrue(dsovf.maybe_cdrom_device("//dev//hda"))

    def test_maybe_cdrom_device_true_on_xvd_partitions(self):
        """Test maybe_cdrom_device returns true on xvd*"""
        self.assertTrue(dsovf.maybe_cdrom_device("/dev/xvda"))
        self.assertTrue(dsovf.maybe_cdrom_device("/dev/xvda1"))
        self.assertTrue(dsovf.maybe_cdrom_device("xvdza1"))


@mock.patch(MPATH + "subp.which")
@mock.patch(MPATH + "subp.subp")
class TestTransportVmwareGuestinfo(CiTestCase):
    """Test the com.vmware.guestInfo transport implemented in
    transport_vmware_guestinfo."""

    rpctool = "vmware-rpctool"
    with_logs = True
    rpctool_path = "/not/important/vmware-rpctool"

    def test_without_vmware_rpctool_returns_notfound(self, m_subp, m_which):
        m_which.return_value = None
        self.assertEqual(NOT_FOUND, dsovf.transport_vmware_guestinfo())
        self.assertEqual(
            0,
            m_subp.call_count,
            "subp should not be called if no rpctool in path.",
        )

    def test_notfound_on_exit_code_1(self, m_subp, m_which):
        """If vmware-rpctool exits 1, then must return not found."""
        m_which.return_value = self.rpctool_path
        m_subp.side_effect = subp.ProcessExecutionError(
            stdout="", stderr="No value found", exit_code=1, cmd=["unused"]
        )
        self.assertEqual(NOT_FOUND, dsovf.transport_vmware_guestinfo())
        self.assertEqual(1, m_subp.call_count)
        self.assertNotIn(
            "WARNING",
            self.logs.getvalue(),
            "exit code of 1 by rpctool should not cause warning.",
        )

    def test_notfound_if_no_content_but_exit_zero(self, m_subp, m_which):
        """If vmware-rpctool exited 0 with no stdout is normal not-found.

        This isn't actually a case I've seen. normally on "not found",
        rpctool would exit 1 with 'No value found' on stderr.  But cover
        the case where it exited 0 and just wrote nothing to stdout.
        """
        m_which.return_value = self.rpctool_path
        m_subp.return_value = ("", "")
        self.assertEqual(NOT_FOUND, dsovf.transport_vmware_guestinfo())
        self.assertEqual(1, m_subp.call_count)

    def test_notfound_and_warns_on_unexpected_exit_code(self, m_subp, m_which):
        """If vmware-rpctool exits non zero or 1, warnings should be logged."""
        m_which.return_value = self.rpctool_path
        m_subp.side_effect = subp.ProcessExecutionError(
            stdout=None, stderr="No value found", exit_code=2, cmd=["unused"]
        )
        self.assertEqual(NOT_FOUND, dsovf.transport_vmware_guestinfo())
        self.assertEqual(1, m_subp.call_count)
        self.assertIn(
            "WARNING",
            self.logs.getvalue(),
            "exit code of 2 by rpctool should log WARNING.",
        )

    def test_found_when_guestinfo_present(self, m_subp, m_which):
        """When there is a ovf info, transport should return it."""
        m_which.return_value = self.rpctool_path
        content = fill_properties({})
        m_subp.return_value = (content, "")
        self.assertEqual(content, dsovf.transport_vmware_guestinfo())
        self.assertEqual(1, m_subp.call_count)


#
# vi: ts=4 expandtab
