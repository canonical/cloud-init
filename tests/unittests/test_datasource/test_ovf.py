# Copyright (C) 2016 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64

from .. import helpers as test_helpers

from cloudinit.sources import DataSourceOVF as dsovf

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
    properties = ''.join([indent + l + "\n" for l in lines])
    return template.format(properties=properties)


class TestReadOvfEnv(test_helpers.TestCase):
    def test_with_b64_userdata(self):
        user_data = "#!/bin/sh\necho hello world\n"
        user_data_b64 = base64.b64encode(user_data.encode()).decode()
        props = {"user-data": user_data_b64, "password": "passw0rd",
                 "instance-id": "inst-001"}
        env = fill_properties(props)
        md, ud, cfg = dsovf.read_ovf_environment(env)
        self.assertEqual({"instance-id": "inst-001"}, md)
        self.assertEqual(user_data.encode(), ud)
        self.assertEqual({'password': "passw0rd"}, cfg)

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
        self.assertEqual({'password': "passw0rd"}, cfg)
        self.assertEqual(None, ud)

# vi: ts=4 expandtab
