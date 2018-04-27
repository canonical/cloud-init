# This file is part of cloud-init. See LICENSE file for license information.

from copy import copy
import mock
import os
import shutil
import tempfile
import yaml

from cloudinit.sources import DataSourceMAAS
from cloudinit import url_helper
from cloudinit.tests.helpers import CiTestCase, populate_dir


class TestMAASDataSource(CiTestCase):

    def setUp(self):
        super(TestMAASDataSource, self).setUp()
        # Make a temp directoy for tests to use.
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_seed_dir_valid(self):
        """Verify a valid seeddir is read as such."""

        userdata = b'valid01-userdata'
        data = {'meta-data/instance-id': 'i-valid01',
                'meta-data/local-hostname': 'valid01-hostname',
                'user-data': userdata,
                'public-keys': 'ssh-rsa AAAAB3Nz...aC1yc2E= keyname'}

        my_d = os.path.join(self.tmp, "valid")
        populate_dir(my_d, data)

        ud, md, vd = DataSourceMAAS.read_maas_seed_dir(my_d)

        self.assertEqual(userdata, ud)
        for key in ('instance-id', 'local-hostname'):
            self.assertEqual(data["meta-data/" + key], md[key])

        # verify that 'userdata' is not returned as part of the metadata
        self.assertFalse(('user-data' in md))
        self.assertIsNone(vd)

    def test_seed_dir_valid_extra(self):
        """Verify extra files do not affect seed_dir validity."""

        userdata = b'valid-extra-userdata'
        data = {'meta-data/instance-id': 'i-valid-extra',
                'meta-data/local-hostname': 'valid-extra-hostname',
                'user-data': userdata, 'foo': 'bar'}

        my_d = os.path.join(self.tmp, "valid_extra")
        populate_dir(my_d, data)

        ud, md, _vd = DataSourceMAAS.read_maas_seed_dir(my_d)

        self.assertEqual(userdata, ud)
        for key in ('instance-id', 'local-hostname'):
            self.assertEqual(data['meta-data/' + key], md[key])

        # additional files should not just appear as keys in metadata atm
        self.assertFalse(('foo' in md))

    def test_seed_dir_invalid(self):
        """Verify that invalid seed_dir raises MAASSeedDirMalformed."""

        valid = {'instance-id': 'i-instanceid',
                 'local-hostname': 'test-hostname', 'user-data': ''}

        my_based = os.path.join(self.tmp, "valid_extra")

        # missing 'userdata' file
        my_d = "%s-01" % my_based
        invalid_data = copy(valid)
        del invalid_data['local-hostname']
        populate_dir(my_d, invalid_data)
        self.assertRaises(DataSourceMAAS.MAASSeedDirMalformed,
                          DataSourceMAAS.read_maas_seed_dir, my_d)

        # missing 'instance-id'
        my_d = "%s-02" % my_based
        invalid_data = copy(valid)
        del invalid_data['instance-id']
        populate_dir(my_d, invalid_data)
        self.assertRaises(DataSourceMAAS.MAASSeedDirMalformed,
                          DataSourceMAAS.read_maas_seed_dir, my_d)

    def test_seed_dir_none(self):
        """Verify that empty seed_dir raises MAASSeedDirNone."""

        my_d = os.path.join(self.tmp, "valid_empty")
        self.assertRaises(DataSourceMAAS.MAASSeedDirNone,
                          DataSourceMAAS.read_maas_seed_dir, my_d)

    def test_seed_dir_missing(self):
        """Verify that missing seed_dir raises MAASSeedDirNone."""
        self.assertRaises(DataSourceMAAS.MAASSeedDirNone,
                          DataSourceMAAS.read_maas_seed_dir,
                          os.path.join(self.tmp, "nonexistantdirectory"))

    def mock_read_maas_seed_url(self, data, seed, version="19991231"):
        """mock up readurl to appear as a web server at seed has provided data.
        return what read_maas_seed_url returns."""
        def my_readurl(*args, **kwargs):
            if len(args):
                url = args[0]
            else:
                url = kwargs['url']
            prefix = "%s/%s/" % (seed, version)
            if not url.startswith(prefix):
                raise ValueError("unexpected call %s" % url)

            short = url[len(prefix):]
            if short not in data:
                raise url_helper.UrlError("not found", code=404, url=url)
            return url_helper.StringResponse(data[short])

        # Now do the actual call of the code under test.
        with mock.patch("cloudinit.url_helper.readurl") as mock_readurl:
            mock_readurl.side_effect = my_readurl
            return DataSourceMAAS.read_maas_seed_url(seed, version=version)

    def test_seed_url_valid(self):
        """Verify that valid seed_url is read as such."""
        valid = {
            'meta-data/instance-id': 'i-instanceid',
            'meta-data/local-hostname': 'test-hostname',
            'meta-data/public-keys': 'test-hostname',
            'meta-data/vendor-data': b'my-vendordata',
            'user-data': b'foodata',
        }
        my_seed = "http://example.com/xmeta"
        my_ver = "1999-99-99"
        ud, md, vd = self.mock_read_maas_seed_url(valid, my_seed, my_ver)

        self.assertEqual(valid['meta-data/instance-id'], md['instance-id'])
        self.assertEqual(
            valid['meta-data/local-hostname'], md['local-hostname'])
        self.assertEqual(valid['meta-data/public-keys'], md['public-keys'])
        self.assertEqual(valid['user-data'], ud)
        # vendor-data is yaml, which decodes a string
        self.assertEqual(valid['meta-data/vendor-data'].decode(), vd)

    def test_seed_url_vendor_data_dict(self):
        expected_vd = {'key1': 'value1'}
        valid = {
            'meta-data/instance-id': 'i-instanceid',
            'meta-data/local-hostname': 'test-hostname',
            'meta-data/vendor-data': yaml.safe_dump(expected_vd).encode(),
        }
        _ud, md, vd = self.mock_read_maas_seed_url(
            valid, "http://example.com/foo")

        self.assertEqual(valid['meta-data/instance-id'], md['instance-id'])
        self.assertEqual(expected_vd, vd)


@mock.patch("cloudinit.sources.DataSourceMAAS.url_helper.OauthUrlHelper")
class TestGetOauthHelper(CiTestCase):
    with_logs = True
    base_cfg = {'consumer_key': 'FAKE_CONSUMER_KEY',
                'token_key': 'FAKE_TOKEN_KEY',
                'token_secret': 'FAKE_TOKEN_SECRET',
                'consumer_secret': None}

    def test_all_required(self, m_helper):
        """Valid config as expected."""
        DataSourceMAAS.get_oauth_helper(self.base_cfg.copy())
        m_helper.assert_has_calls([mock.call(**self.base_cfg)])

    def test_other_fields_not_passed_through(self, m_helper):
        """Only relevant fields are passed through."""
        mycfg = self.base_cfg.copy()
        mycfg['unrelated_field'] = 'unrelated'
        DataSourceMAAS.get_oauth_helper(mycfg)
        m_helper.assert_has_calls([mock.call(**self.base_cfg)])


class TestGetIdHash(CiTestCase):
    v1_cfg = {'consumer_key': 'CKEY', 'token_key': 'TKEY',
              'token_secret': 'TSEC'}
    v1_id = (
        'v1:'
        '403ee5f19c956507f1d0e50814119c405902137ea4f8838bde167c5da8110392')

    def test_v1_expected(self):
        """Test v1 id generated as expected working behavior from config."""
        result = DataSourceMAAS.get_id_from_ds_cfg(self.v1_cfg.copy())
        self.assertEqual(self.v1_id, result)

    def test_v1_extra_fields_are_ignored(self):
        """Test v1 id ignores unused entries in config."""
        cfg = self.v1_cfg.copy()
        cfg['consumer_secret'] = "BOO"
        cfg['unrelated'] = "HI MOM"
        result = DataSourceMAAS.get_id_from_ds_cfg(cfg)
        self.assertEqual(self.v1_id, result)


# vi: ts=4 expandtab
