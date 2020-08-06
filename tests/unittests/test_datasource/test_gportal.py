# Author: Alexander Birkner <alexander.birkner@g-portal.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import json

from cloudinit.sources import DataSourceGPortal
from cloudinit import settings
from cloudinit import helpers

from cloudinit.tests.helpers import mock, CiTestCase

METADATA = json.loads("""
{
  "id": "3f657fa2-7b72-466e-bad4-f83a31fbe5cd",
  "type": "BARE_METAL",  
  "fqdn": "server1",
  "region": "FRA01",
  "public_keys": [
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCdggAqqRKDj8X9ckZzJ0tB/r/VF6pD5JqP6c2/BHL9ctSae5TQClyOpSJdbp395MCjF3xOe89uK2MeOzUsYNMsTrwYPpFfpndnyAmY8Dc8L/iniqtFnHBCFS+z5VAx1mZNHdRS3NEhTkzPrt7PdmcJ1+cyfrUo9+w3kJMLuc3iyj5ZsoAp7anGtQKLCCxIL5fFCAQcYZR8w/AvLIj4B8sCb6Mon4TF9QhAJB1KbUhEwe3PY3tP1IkjYve9mKM6D5JF/b27ylRvliLLiq92LD/tBjJWjAaw92BqC3fa+Yfx9O+bCrNyP2yFX15L3/nbkppxmlZkk7aHuovkc3W6I5FlcbQfXMUjmMafdA/5Kmss5mgoq0q0E5nWhUu4L2NMW5VAkeTv+lsWLhj1vCo9JC3408mgiNaUn0XNq+uC4J6nXF/qYFNq5XvJPDsaxcxDBJip9dl9a/5BGbo6gAfORMJ1NTzpumKlEIoWZjk/TYVP7Za81UppUkk/n5x8spN70ZxoSIjQ8mXsY/GJ0uAycmy8UYH2hnDmNXiFFEh2E3iDwHYxUaoCVy/kwKBZc7kf1Rc3Fnf+Bt0PU2+k3msqBbpej3ZIoHGMdAaHpI6yYj6c60HC6PYClskkFufbGqyAtN6DcnDD3BthHS096BaTvwpIRRpyrYcPBs4gAccDbX//qw==",
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDEWZnqgDcJhyK1x7m5X6FNDIeBqM/ekFQbBUreIUW8b2pOhG1ldymCBXWONfhauuNonf9+tz1pEYNzSN7JBpHZYEraETjs32mV+X8ufHdLJhTxUM6KTjfFRRihYEHlD60URZtPFKxQStyue7s9YK02nVTALll1TyuV4wKfkP51V3AFMFjxw00i2swT19RhRTYNYzl8i7E8K14oMDEMFYlmLMeuOMpqJoORvZUX+lBKqn9eLsQmah4LssdVzP0bxMZXCGh+4j9XCk2eroyCgh7lO+obQlZxjltUIXLU/+UtOJIItpI3/2Ux/G8NCZ/FoZllIZwWuEJtB95mSX0g1uLDqSmgTbmvO56njQ8oC/KZMlX1IEEM56uUzPeLpQkclw6EEDsXLGhYn8S44u4PSYdC7DhprbRwNVbfgzfbpfnSSrqbnf1Z0ZugYT+0i8zx5ZyTHDiuN7dvvE8zVW/Oza+DZCctPsFW5RZIQiUENcJdf/NioCCgzJO8slh1RKc8lHpkxyN6YlbY6TbNv9x9Fpi5tHUI1vSeIQ75wTBrTIecIjNJNWZAkqQn2TVwdL6r2FG6Q/Avz2brCybUcNb0Pem3kn9BWrACbN1KPPRb9/iY+3wun8Bzq7CV9/JDrtgzCwFXM44fFiUnzYQgfvG9VpLvq8IVpIFhNlQAvkkNaLZuww=="
  ],
  "interfaces": {
    "public": [
      {
        "ipv4": {
          "address": "176.57.186.5",
          "netmask": "255.255.255.0",
          "gateway": "176.57.186.1"
        },
        "mac": "40:9a:4c:8d:96:77",
        "type": "public"
      }
    ]
  },
  "dns": {
    "nameservers": [
      "8.8.8.8",
      "1.1.1.1"
    ]
  }
}
""")  # noqa: W291, E501


def _mock_dmi():
    return True, METADATA.get('id')


class TestDataSourceGPortal(CiTestCase):
    """
    Test reading the meta-data
    """
    def setUp(self):
        super(TestDataSourceGPortal, self).setUp()
        self.tmp = self.tmp_dir()

    def get_ds(self, get_sysinfo=_mock_dmi):
        ds = DataSourceGPortal.DataSourceGPortal(
            settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': self.tmp}))
        if get_sysinfo is not None:
            ds._get_sysinfo = get_sysinfo
        return ds

    @mock.patch('cloudinit.sources.helpers.gportal.load_metadata')
    def test_metadata(self, mock_loadmd):
        mock_loadmd.return_value = METADATA.copy()

        ds = self.get_ds()
        ret = ds.get_data()
        self.assertTrue(ret)

        assert 0 != mock_loadmd.call_count

        self.assertEqual(METADATA.get('user_data'), ds.get_userdata_raw())
        self.assertEqual(METADATA.get('vendor_data'), ds.get_vendordata_raw())
        self.assertEqual(METADATA.get('region'), ds.availability_zone)
        self.assertEqual(METADATA.get('id'), ds.get_instance_id())
        self.assertEqual(METADATA.get('fqdn'), ds.get_hostname())

        self.assertIsInstance(ds.get_public_ssh_keys(), list)
        self.assertEqual(METADATA.get('public_keys'),
                         ds.get_public_ssh_keys())
