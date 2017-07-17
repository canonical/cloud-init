# This file is part of cloud-init. See LICENSE file for license information.

import httpretty
import mock

from .. import helpers as test_helpers
from cloudinit import helpers
from cloudinit.sources import DataSourceEc2 as ec2


# collected from api version 2009-04-04/ with
# python3 -c 'import json
# from cloudinit.ec2_utils import get_instance_metadata as gm
# print(json.dumps(gm("2009-04-04"), indent=1, sort_keys=True))'
DEFAULT_METADATA = {
    "ami-id": "ami-80861296",
    "ami-launch-index": "0",
    "ami-manifest-path": "(unknown)",
    "block-device-mapping": {"ami": "/dev/sda1", "root": "/dev/sda1"},
    "hostname": "ip-10-0-0-149",
    "instance-action": "none",
    "instance-id": "i-0052913950685138c",
    "instance-type": "t2.micro",
    "local-hostname": "ip-10-0-0-149",
    "local-ipv4": "10.0.0.149",
    "placement": {"availability-zone": "us-east-1b"},
    "profile": "default-hvm",
    "public-hostname": "",
    "public-ipv4": "107.23.188.247",
    "public-keys": {"brickies": ["ssh-rsa AAAAB3Nz....w== brickies"]},
    "reservation-id": "r-00a2c173fb5782a08",
    "security-groups": "wide-open"
}


def _register_ssh_keys(rfunc, base_url, keys_data):
    """handle ssh key inconsistencies.

    public-keys in the ec2 metadata is inconsistently formatted compared
    to other entries.
    Given keys_data of {name1: pubkey1, name2: pubkey2}

    This registers the following urls:
       base_url                 0={name1}\n1={name2} # (for each name)
       base_url/                0={name1}\n1={name2} # (for each name)
       base_url/0               openssh-key
       base_url/0/              openssh-key
       base_url/0/openssh-key   {pubkey1}
       base_url/0/openssh-key/  {pubkey1}
       ...
    """

    base_url = base_url.rstrip("/")
    odd_index = '\n'.join(
        ["{0}={1}".format(n, name)
         for n, name in enumerate(sorted(keys_data))])

    rfunc(base_url, odd_index)
    rfunc(base_url + "/", odd_index)

    for n, name in enumerate(sorted(keys_data)):
        val = keys_data[name]
        if isinstance(val, list):
            val = '\n'.join(val)
        burl = base_url + "/%s" % n
        rfunc(burl, "openssh-key")
        rfunc(burl + "/", "openssh-key")
        rfunc(burl + "/%s/openssh-key" % name, val)
        rfunc(burl + "/%s/openssh-key/" % name, val)


def register_mock_metaserver(base_url, data):
    """Register with httpretty a ec2 metadata like service serving 'data'.

    If given a dictionary, it will populate urls under base_url for
    that dictionary.  For example, input of
       {"instance-id": "i-abc", "mac": "00:16:3e:00:00:00"}
    populates
       base_url  with 'instance-id\nmac'
       base_url/ with 'instance-id\nmac'
       base_url/instance-id with i-abc
       base_url/mac with 00:16:3e:00:00:00
    In the index, references to lists or dictionaries have a trailing /.
    """
    def register_helper(register, base_url, body):
        base_url = base_url.rstrip("/")
        if isinstance(body, str):
            register(base_url, body)
        elif isinstance(body, list):
            register(base_url, '\n'.join(body) + '\n')
            register(base_url + '/', '\n'.join(body) + '\n')
        elif isinstance(body, dict):
            vals = []
            for k, v in body.items():
                if k == 'public-keys':
                    _register_ssh_keys(
                        register, base_url + '/public-keys/', v)
                    continue
                suffix = k.rstrip("/")
                if not isinstance(v, (str, list)):
                    suffix += "/"
                vals.append(suffix)
                url = base_url + '/' + suffix
                register_helper(register, url, v)
            register(base_url, '\n'.join(vals) + '\n')
            register(base_url + '/', '\n'.join(vals) + '\n')
        elif body is None:
            register(base_url, 'not found', status_code=404)

    def myreg(*argc, **kwargs):
        # print("register_url(%s, %s)" % (argc, kwargs))
        return httpretty.register_uri(httpretty.GET, *argc, **kwargs)

    register_helper(myreg, base_url, data)


class TestEc2(test_helpers.HttprettyTestCase):
    valid_platform_data = {
        'uuid': 'ec212f79-87d1-2f1d-588f-d86dc0fd5412',
        'uuid_source': 'dmi',
        'serial': 'ec212f79-87d1-2f1d-588f-d86dc0fd5412',
    }

    def setUp(self):
        super(TestEc2, self).setUp()
        self.metadata_addr = ec2.DataSourceEc2.metadata_urls[0]
        self.api_ver = '2009-04-04'

    @property
    def metadata_url(self):
        return '/'.join([self.metadata_addr, self.api_ver, 'meta-data', ''])

    @property
    def userdata_url(self):
        return '/'.join([self.metadata_addr, self.api_ver, 'user-data'])

    def _patch_add_cleanup(self, mpath, *args, **kwargs):
        p = mock.patch(mpath, *args, **kwargs)
        p.start()
        self.addCleanup(p.stop)

    def _setup_ds(self, sys_cfg, platform_data, md, ud=None):
        distro = {}
        paths = helpers.Paths({})
        if sys_cfg is None:
            sys_cfg = {}
        ds = ec2.DataSourceEc2(sys_cfg=sys_cfg, distro=distro, paths=paths)
        if platform_data is not None:
            self._patch_add_cleanup(
                "cloudinit.sources.DataSourceEc2._collect_platform_data",
                return_value=platform_data)

        if md:
            register_mock_metaserver(self.metadata_url, md)
            register_mock_metaserver(self.userdata_url, ud)

        return ds

    @httpretty.activate
    def test_valid_platform_with_strict_true(self):
        """Valid platform data should return true with strict_id true."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': True}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertEqual(True, ret)

    @httpretty.activate
    def test_valid_platform_with_strict_false(self):
        """Valid platform data should return true with strict_id false."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': False}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertEqual(True, ret)

    @httpretty.activate
    def test_unknown_platform_with_strict_true(self):
        """Unknown platform data with strict_id true should return False."""
        uuid = 'ab439480-72bf-11d3-91fc-b8aded755F9a'
        ds = self._setup_ds(
            platform_data={'uuid': uuid, 'uuid_source': 'dmi', 'serial': ''},
            sys_cfg={'datasource': {'Ec2': {'strict_id': True}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertEqual(False, ret)

    @httpretty.activate
    def test_unknown_platform_with_strict_false(self):
        """Unknown platform data with strict_id false should return True."""
        uuid = 'ab439480-72bf-11d3-91fc-b8aded755F9a'
        ds = self._setup_ds(
            platform_data={'uuid': uuid, 'uuid_source': 'dmi', 'serial': ''},
            sys_cfg={'datasource': {'Ec2': {'strict_id': False}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertEqual(True, ret)


# vi: ts=4 expandtab
