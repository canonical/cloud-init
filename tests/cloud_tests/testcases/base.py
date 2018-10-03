# This file is part of cloud-init. See LICENSE file for license information.

"""Base test case module."""

import crypt
import json
import re
import unittest2


from cloudinit import util as c_util

SkipTest = unittest2.SkipTest


class CloudTestCase(unittest2.TestCase):
    """Base test class for verifiers."""

    # data gets populated in get_suite.setUpClass
    data = {}
    conf = None
    _cloud_config = None
    release_conf = {}    # The platform's os release configuration

    expected_warnings = ()  # Subclasses set to ignore expected WARN logs

    @property
    def os_cfg(self):
        return self.release_conf[self.os_name]['default']

    def is_distro(self, distro_name):
        return self.os_cfg['os'] == distro_name

    @classmethod
    def maybeSkipTest(cls):
        """Present to allow subclasses to override and raise a skipTest."""
        pass

    def assertPackageInstalled(self, name, version=None):
        """Check dpkg-query --show output for matching package name.

        @param name: package base name
        @param version: string representing a package version or part of a
            version.
        """
        pkg_out = self.get_data_file('package-versions')
        pkg_match = re.search(
            '^%s\t(?P<version>.*)$' % name, pkg_out, re.MULTILINE)
        if pkg_match:
            installed_version = pkg_match.group('version')
            if not version:
                return  # Success
            if installed_version.startswith(version):
                return  # Success
            raise AssertionError(
                'Expected package version %s-%s not found. Found %s' %
                name, version, installed_version)
        raise AssertionError('Package not installed: %s' % name)

    def os_version_cmp(self, cmp_version):
        """Compare the version of the test to comparison_version.

        @param: cmp_version: Either a float or a string representing
           a release os from releases.yaml (e.g. centos66)

        @return: -1 when version < cmp_version, 0 when version=cmp_version and
            1 when version > cmp_version.
        """
        version = self.release_conf[self.os_name]['default']['version']
        if isinstance(cmp_version, str):
            cmp_version = self.release_conf[cmp_version]['default']['version']
        if version < cmp_version:
            return -1
        elif version == cmp_version:
            return 0
        else:
            return 1

    @property
    def os_name(self):
        return self.data.get('os_name', 'UNKNOWN')

    @property
    def platform(self):
        return self.data.get('platform', 'UNKNOWN')

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

    def get_data_file(self, name, decode=True):
        """Get data file failing test if it is not present."""
        if name not in self.data:
            raise AssertionError('File "{}" missing from collect data'
                                 .format(name))
        if not decode:
            return self.data[name]
        return self.data[name].decode('utf-8')

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
        """Unexpected warnings should not be found in the log."""
        warnings = [
            l for l in self.get_data_file('cloud-init.log').splitlines()
            if 'WARN' in l]
        joined_warnings = '\n'.join(warnings)
        for expected_warning in self.expected_warnings:
            self.assertIn(
                expected_warning, joined_warnings,
                msg="Did not find %s in cloud-init.log" % expected_warning)
            # Prune expected from discovered warnings
            warnings = [w for w in warnings if expected_warning not in w]
        self.assertEqual(
            [], warnings, msg="'WARN' found inside cloud-init.log")

    def test_instance_data_json_ec2(self):
        """Validate instance-data.json content by ec2 platform.

        This content is sourced by snapd when determining snapstore endpoints.
        We validate expected values per cloud type to ensure we don't break
        snapd.
        """
        if self.platform != 'ec2':
            raise SkipTest(
                'Skipping ec2 instance-data.json on %s' % self.platform)
        out = self.get_data_file('instance-data.json')
        if not out:
            if self.is_distro('ubuntu') and self.os_version_cmp('bionic') >= 0:
                raise AssertionError(
                    'No instance-data.json found on %s' % self.os_name)
            raise SkipTest(
                'Skipping instance-data.json test.'
                ' OS: %s not bionic or newer' % self.os_name)
        instance_data = json.loads(out)
        self.assertItemsEqual(
            [],
            instance_data['base64_encoded_keys'])
        ds = instance_data.get('ds', {})
        v1_data = instance_data.get('v1', {})
        metadata = ds.get('meta_data', {})
        macs = metadata.get(
            'network', {}).get('interfaces', {}).get('macs', {})
        if not macs:
            raise AssertionError('No network data from EC2 meta-data')
        # Check meta-data items we depend on
        expected_net_keys = [
            'public-ipv4s', 'ipv4-associations', 'local-hostname',
            'public-hostname']
        for mac_data in macs.values():
            for key in expected_net_keys:
                self.assertIn(key, mac_data)
        self.assertIsNotNone(
            metadata.get('placement', {}).get('availability-zone'),
            'Could not determine EC2 Availability zone placement')
        self.assertIsNotNone(
            v1_data['availability_zone'], 'expected ec2 availability_zone')
        self.assertEqual('aws', v1_data['cloud_name'])
        self.assertIn('i-', v1_data['instance_id'])
        self.assertIn('ip-', v1_data['local_hostname'])
        self.assertIsNotNone(v1_data['region'], 'expected ec2 region')

    def test_instance_data_json_lxd(self):
        """Validate instance-data.json content by lxd platform.

        This content is sourced by snapd when determining snapstore endpoints.
        We validate expected values per cloud type to ensure we don't break
        snapd.
        """
        if self.platform != 'lxd':
            raise SkipTest(
                'Skipping lxd instance-data.json on %s' % self.platform)
        out = self.get_data_file('instance-data.json')
        if not out:
            if self.is_distro('ubuntu') and self.os_version_cmp('bionic') >= 0:
                raise AssertionError(
                    'No instance-data.json found on %s' % self.os_name)
            raise SkipTest(
                'Skipping instance-data.json test.'
                ' OS: %s not bionic or newer' % self.os_name)
        instance_data = json.loads(out)
        v1_data = instance_data.get('v1', {})
        self.assertItemsEqual([], sorted(instance_data['base64_encoded_keys']))
        self.assertEqual('nocloud', v1_data['cloud_name'])
        self.assertIsNone(
            v1_data['availability_zone'],
            'found unexpected lxd availability_zone %s' %
            v1_data['availability_zone'])
        self.assertIn('cloud-test', v1_data['instance_id'])
        self.assertIn('cloud-test', v1_data['local_hostname'])
        self.assertIsNone(
            v1_data['region'],
            'found unexpected lxd region %s' % v1_data['region'])

    def test_instance_data_json_kvm(self):
        """Validate instance-data.json content by nocloud-kvm platform.

        This content is sourced by snapd when determining snapstore endpoints.
        We validate expected values per cloud type to ensure we don't break
        snapd.
        """
        if self.platform != 'nocloud-kvm':
            raise SkipTest(
                'Skipping nocloud-kvm instance-data.json on %s' %
                self.platform)
        out = self.get_data_file('instance-data.json')
        if not out:
            if self.is_distro('ubuntu') and self.os_version_cmp('bionic') >= 0:
                raise AssertionError(
                    'No instance-data.json found on %s' % self.os_name)
            raise SkipTest(
                'Skipping instance-data.json test.'
                ' OS: %s not bionic or newer' % self.os_name)
        instance_data = json.loads(out)
        v1_data = instance_data.get('v1', {})
        self.assertItemsEqual([], instance_data['base64_encoded_keys'])
        self.assertEqual('nocloud', v1_data['cloud_name'])
        self.assertIsNone(
            v1_data['availability_zone'],
            'found unexpected kvm availability_zone %s' %
            v1_data['availability_zone'])
        self.assertIsNotNone(
            re.match(r'[\da-f]{8}(-[\da-f]{4}){3}-[\da-f]{12}',
                     v1_data['instance_id']),
            'kvm instance_id is not a UUID: %s' % v1_data['instance_id'])
        self.assertIn('ubuntu', v1_data['local_hostname'])
        self.assertIsNone(
            v1_data['region'],
            'found unexpected lxd region %s' % v1_data['region'])


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
