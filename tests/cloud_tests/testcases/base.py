# This file is part of cloud-init. See LICENSE file for license information.

"""Base test case module."""

import crypt
import json
import unittest

from cloudinit import util as c_util


class CloudTestCase(unittest.TestCase):
    """Base test class for verifiers."""

    data = None
    conf = None
    _cloud_config = None

    @property
    def cloud_config(self):
        """Get the cloud-config used by the test."""
        if not self._cloud_config:
            self._cloud_config = c_util.load_yaml(self.conf)
        return self._cloud_config

    def get_config_entry(self, name):
        """Get a config entry from cloud-config ensuring that it is present."""
        if name not in self.cloud_config:
            raise AssertionError('Key "{}" not in cloud config'.format(name))
        return self.cloud_config[name]

    def get_data_file(self, name):
        """Get data file failing test if it is not present."""
        if name not in self.data:
            raise AssertionError('File "{}" missing from collect data'
                                 .format(name))
        return self.data[name]

    def get_instance_id(self):
        """Get recorded instance id."""
        return self.get_data_file('instance-id').strip()

    def get_status_data(self, data, version=None):
        """Parse result.json and status.json like data files.

        @param data: data to load
        @param version: cloud-init output version, defaults to 'v1'
        @return_value: dict of data or None if missing
        """
        if not version:
            version = 'v1'
        data = json.loads(data)
        return data.get(version)

    def get_datasource(self):
        """Get datasource name."""
        data = self.get_status_data(self.get_data_file('result.json'))
        return data.get('datasource')

    def test_no_stages_errors(self):
        """Ensure that there were no errors in any stage."""
        status = self.get_status_data(self.get_data_file('status.json'))
        for stage in ('init', 'init-local', 'modules-config', 'modules-final'):
            self.assertIn(stage, status)
            self.assertEqual(len(status[stage]['errors']), 0,
                             'errors {} were encountered in stage {}'
                             .format(status[stage]['errors'], stage))
        result = self.get_status_data(self.get_data_file('result.json'))
        self.assertEqual(len(result['errors']), 0)

    def test_no_warnings_in_log(self):
        """Warnings should not be found in the log."""
        self.assertEqual(
            [],
            [l for l in self.get_data_file('cloud-init.log').splitlines()
             if 'WARN' in l],
            msg="'WARN' found inside cloud-init.log")


class PasswordListTest(CloudTestCase):
    """Base password test case class."""

    def test_shadow_passwords(self):
        """Test shadow passwords."""
        shadow = self.get_data_file('shadow')
        users = {}
        dupes = []
        for line in shadow.splitlines():
            user, encpw = line.split(":")[0:2]
            if user in users:
                dupes.append(user)
            users[user] = encpw

        jane_enc = "$5$iW$XsxmWCdpwIW8Yhv.Jn/R3uk6A4UaicfW5Xp7C9p9pg."
        self.assertEqual([], dupes)
        self.assertEqual(jane_enc, users['jane'])

        mikey_enc = "$5$xZ$B2YGGEx2AOf4PeW48KC6.QyT1W2B4rZ9Qbltudtha89"
        self.assertEqual(mikey_enc, users['mikey'])

        # shadow entry is $N$salt$, so we encrypt with the same format
        # and salt and expect the result.
        tom = "mypassword123!"
        fmtsalt = users['tom'][0:users['tom'].rfind("$") + 1]
        tom_enc = crypt.crypt(tom, fmtsalt)
        self.assertEqual(tom_enc, users['tom'])

        harry_enc = ("$6$LF$9Z2p6rWK6TNC1DC6393ec0As.18KRAvKDbfsG"
                     "JEdWN3sRQRwpdfoh37EQ3yUh69tP4GSrGW5XKHxMLiKowJgm/")
        dick_enc = "$1$ssisyfpf$YqvuJLfrrW6Cg/l53Pi1n1"

        # these should have been changed to random values.
        self.assertNotEqual(harry_enc, users['harry'])
        self.assertTrue(users['harry'].startswith("$"))
        self.assertNotEqual(dick_enc, users['dick'])
        self.assertTrue(users['dick'].startswith("$"))

        self.assertNotEqual(users['harry'], users['dick'])

    def test_shadow_expected_users(self):
        """Test every tom, dick, and harry user in shadow."""
        out = self.get_data_file('shadow')
        self.assertIn('tom:', out)
        self.assertIn('dick:', out)
        self.assertIn('harry:', out)
        self.assertIn('jane:', out)
        self.assertIn('mikey:', out)

    def test_sshd_config(self):
        """Test sshd config allows passwords."""
        out = self.get_data_file('sshd_config')
        self.assertIn('PasswordAuthentication yes', out)

# vi: ts=4 expandtab
