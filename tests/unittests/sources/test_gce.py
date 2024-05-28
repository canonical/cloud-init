# Copyright (C) 2014 Vaidas Jablonskis
#
# Author: Vaidas Jablonskis <jablonskis@gmail.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import datetime
import json
import re
from base64 import b64decode, b64encode
from unittest import mock
from urllib.parse import urlparse

import responses

from cloudinit import distros, helpers, settings
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.sources import DataSourceGCE
from tests.unittests import helpers as test_helpers

M_PATH = "cloudinit.sources.DataSourceGCE."

GCE_META = {
    "instance/id": "123",
    "instance/zone": "foo/bar",
    "instance/hostname": "server.project-foo.local",
}

GCE_META_PARTIAL = {
    "instance/id": "1234",
    "instance/hostname": "server.project-bar.local",
    "instance/zone": "bar/baz",
}

GCE_META_ENCODING = {
    "instance/id": "12345",
    "instance/hostname": "server.project-baz.local",
    "instance/zone": "baz/bang",
    "instance/attributes": {
        "user-data": b64encode(b"#!/bin/echo baz\n").decode("utf-8"),
        "user-data-encoding": "base64",
    },
}

GCE_USER_DATA_TEXT = {
    "instance/id": "12345",
    "instance/hostname": "server.project-baz.local",
    "instance/zone": "baz/bang",
    "instance/attributes": {
        "user-data": "#!/bin/sh\necho hi mom\ntouch /run/up-now\n",
    },
}

HEADERS = {"Metadata-Flavor": "Google"}
MD_URL_RE = re.compile(
    r"http://metadata.google.internal/computeMetadata/v1/.*"
)
GUEST_ATTRIBUTES_URL = (
    "http://metadata.google.internal/computeMetadata/"
    "v1/instance/guest-attributes/hostkeys/"
)


class TestDataSourceGCE(test_helpers.ResponsesTestCase):
    with_logs = True

    def _make_distro(self, dtype, def_user=None):
        cfg = dict(settings.CFG_BUILTIN)
        cfg["system_info"]["distro"] = dtype
        paths = helpers.Paths(cfg["system_info"]["paths"])
        distro_cls = distros.fetch(dtype)
        if def_user:
            cfg["system_info"]["default_user"] = def_user.copy()
        distro = distro_cls(dtype, cfg["system_info"], paths)
        return distro

    def setUp(self):
        tmp = self.tmp_dir()
        self.ds = DataSourceGCE.DataSourceGCE(
            settings.CFG_BUILTIN, None, helpers.Paths({"run_dir": tmp})
        )

        ppatch = self.m_platform_reports_gce = mock.patch(
            M_PATH + "platform_reports_gce"
        )
        self.m_platform_reports_gce = ppatch.start()
        self.m_platform_reports_gce.return_value = True
        self.addCleanup(ppatch.stop)

        pppatch = self.m_is_resolvable_url = mock.patch(
            M_PATH + "util.is_resolvable_url", return_value=True
        )
        self.m_is_resolvable_url = pppatch.start()
        self.addCleanup(pppatch.stop)

        self.add_patch("time.sleep", "m_sleep")  # just to speed up tests
        super(TestDataSourceGCE, self).setUp()

    def _set_mock_metadata(self, gce_meta=None, *, check_headers=None):
        if gce_meta is None:
            gce_meta = GCE_META

        def _request_callback(request):
            recursive = False
            url_path = urlparse(request.url).path
            if url_path.startswith("/computeMetadata/v1/"):
                path = url_path.split("/computeMetadata/v1/")[1:][0]
                recursive = path.endswith("/")
                path = path.rstrip("/")
            else:
                path = None
            if path in gce_meta:
                response = gce_meta.get(path)
                if recursive:
                    response = json.dumps(response)
                if check_headers is not None:
                    for k in check_headers.keys():
                        self.assertEqual(check_headers[k], request.headers[k])
                return (200, request.headers, response)
            else:
                return (404, request.headers, "")

        self.responses.add_callback(
            responses.GET,
            MD_URL_RE,
            callback=_request_callback,
        )

    def test_connection(self):
        self._set_mock_metadata(check_headers=HEADERS)
        success = self.ds.get_data()
        self.assertTrue(success)

    def test_metadata(self):
        # UnicodeDecodeError if set to ds.userdata instead of userdata_raw
        meta = GCE_META.copy()
        meta["instance/attributes/user-data"] = b"/bin/echo \xff\n"

        self._set_mock_metadata()
        self.ds.get_data()

        shostname = GCE_META.get("instance/hostname").split(".")[0]
        self.assertEqual(shostname, self.ds.get_hostname().hostname)

        self.assertEqual(
            GCE_META.get("instance/id"), self.ds.get_instance_id()
        )

        self.assertEqual(
            GCE_META.get("instance/attributes/user-data"),
            self.ds.get_userdata_raw(),
        )

    def test_metadata_partial(self):
        """test partial metadata (missing user-data in particular)"""
        self._set_mock_metadata(GCE_META_PARTIAL)
        self.ds.get_data()

        self.assertEqual(
            GCE_META_PARTIAL.get("instance/id"), self.ds.get_instance_id()
        )

        shostname = GCE_META_PARTIAL.get("instance/hostname").split(".")[0]
        self.assertEqual(shostname, self.ds.get_hostname().hostname)

    def test_userdata_no_encoding(self):
        """check that user-data is read."""
        self._set_mock_metadata(GCE_USER_DATA_TEXT)
        self.ds.get_data()
        self.assertEqual(
            GCE_USER_DATA_TEXT["instance/attributes"]["user-data"].encode(),
            self.ds.get_userdata_raw(),
        )

    def test_metadata_encoding(self):
        """user-data is base64 encoded if user-data-encoding is 'base64'."""
        self._set_mock_metadata(GCE_META_ENCODING)
        self.ds.get_data()

        instance_data = GCE_META_ENCODING.get("instance/attributes")
        decoded = b64decode(instance_data.get("user-data"))
        self.assertEqual(decoded, self.ds.get_userdata_raw())

    def test_missing_required_keys_return_false(self):
        for required_key in [
            "instance/id",
            "instance/zone",
            "instance/hostname",
        ]:
            meta = GCE_META_PARTIAL.copy()
            del meta[required_key]
            self._set_mock_metadata(meta)
            self.assertEqual(False, self.ds.get_data())
            self.responses.reset()

    def test_no_ssh_keys_metadata(self):
        self._set_mock_metadata()
        self.ds.get_data()
        self.assertEqual([], self.ds.get_public_ssh_keys())

    def test_cloudinit_ssh_keys(self):
        valid_key = "ssh-rsa VALID {0}"
        invalid_key = "ssh-rsa INVALID {0}"
        project_attributes = {
            "sshKeys": "\n".join(
                [
                    "cloudinit:{0}".format(valid_key.format(0)),
                    "user:{0}".format(invalid_key.format(0)),
                ]
            ),
            "ssh-keys": "\n".join(
                [
                    "cloudinit:{0}".format(valid_key.format(1)),
                    "user:{0}".format(invalid_key.format(1)),
                ]
            ),
        }
        instance_attributes = {
            "ssh-keys": "\n".join(
                [
                    "cloudinit:{0}".format(valid_key.format(2)),
                    "user:{0}".format(invalid_key.format(2)),
                ]
            ),
            "block-project-ssh-keys": "False",
        }

        meta = GCE_META.copy()
        meta["project/attributes"] = project_attributes
        meta["instance/attributes"] = instance_attributes

        self._set_mock_metadata(meta)
        self.ds.get_data()

        expected = [valid_key.format(key) for key in range(3)]
        self.assertEqual(set(expected), set(self.ds.get_public_ssh_keys()))

    @mock.patch(M_PATH + "ug_util")
    def test_default_user_ssh_keys(self, mock_ug_util):
        mock_ug_util.normalize_users_groups.return_value = None, None
        mock_ug_util.extract_default.return_value = "ubuntu", None
        ubuntu_ds = DataSourceGCE.DataSourceGCE(
            settings.CFG_BUILTIN,
            self._make_distro("ubuntu"),
            helpers.Paths({"run_dir": self.tmp_dir()}),
        )

        valid_key = "ssh-rsa VALID {0}"
        invalid_key = "ssh-rsa INVALID {0}"
        project_attributes = {
            "sshKeys": "\n".join(
                [
                    "ubuntu:{0}".format(valid_key.format(0)),
                    "user:{0}".format(invalid_key.format(0)),
                ]
            ),
            "ssh-keys": "\n".join(
                [
                    "ubuntu:{0}".format(valid_key.format(1)),
                    "user:{0}".format(invalid_key.format(1)),
                ]
            ),
        }
        instance_attributes = {
            "ssh-keys": "\n".join(
                [
                    "ubuntu:{0}".format(valid_key.format(2)),
                    "user:{0}".format(invalid_key.format(2)),
                ]
            ),
            "block-project-ssh-keys": "False",
        }

        meta = GCE_META.copy()
        meta["project/attributes"] = project_attributes
        meta["instance/attributes"] = instance_attributes

        self._set_mock_metadata(meta)
        ubuntu_ds.get_data()

        expected = [valid_key.format(key) for key in range(3)]
        self.assertEqual(set(expected), set(ubuntu_ds.get_public_ssh_keys()))

    def test_instance_ssh_keys_override(self):
        valid_key = "ssh-rsa VALID {0}"
        invalid_key = "ssh-rsa INVALID {0}"
        project_attributes = {
            "sshKeys": "cloudinit:{0}".format(invalid_key.format(0)),
            "ssh-keys": "cloudinit:{0}".format(invalid_key.format(1)),
        }
        instance_attributes = {
            "sshKeys": "cloudinit:{0}".format(valid_key.format(0)),
            "ssh-keys": "cloudinit:{0}".format(valid_key.format(1)),
            "block-project-ssh-keys": "False",
        }

        meta = GCE_META.copy()
        meta["project/attributes"] = project_attributes
        meta["instance/attributes"] = instance_attributes

        self._set_mock_metadata(meta)
        self.ds.get_data()

        expected = [valid_key.format(key) for key in range(2)]
        self.assertEqual(set(expected), set(self.ds.get_public_ssh_keys()))

    def test_block_project_ssh_keys_override(self):
        valid_key = "ssh-rsa VALID {0}"
        invalid_key = "ssh-rsa INVALID {0}"
        project_attributes = {
            "sshKeys": "cloudinit:{0}".format(invalid_key.format(0)),
            "ssh-keys": "cloudinit:{0}".format(invalid_key.format(1)),
        }
        instance_attributes = {
            "ssh-keys": "cloudinit:{0}".format(valid_key.format(0)),
            "block-project-ssh-keys": "True",
        }

        meta = GCE_META.copy()
        meta["project/attributes"] = project_attributes
        meta["instance/attributes"] = instance_attributes

        self._set_mock_metadata(meta)
        self.ds.get_data()

        expected = [valid_key.format(0)]
        self.assertEqual(set(expected), set(self.ds.get_public_ssh_keys()))

    def test_only_last_part_of_zone_used_for_availability_zone(self):
        self._set_mock_metadata()
        r = self.ds.get_data()
        self.assertEqual(True, r)
        self.assertEqual("bar", self.ds.availability_zone)

    @mock.patch("cloudinit.sources.DataSourceGCE.GoogleMetadataFetcher")
    def test_get_data_returns_false_if_not_on_gce(self, m_fetcher):
        self.m_platform_reports_gce.return_value = False
        ret = self.ds.get_data()
        self.assertEqual(False, ret)
        m_fetcher.assert_not_called()

    def test_has_expired(self):
        def _get_timestamp(days):
            format_str = "%Y-%m-%dT%H:%M:%S+0000"
            today = datetime.datetime.now()
            timestamp = today + datetime.timedelta(days=days)
            return timestamp.strftime(format_str)

        past = _get_timestamp(-1)
        future = _get_timestamp(1)
        ssh_keys = {
            None: False,
            "": False,
            "Invalid": False,
            "user:ssh-rsa key user@domain.com": False,
            'user:ssh-rsa key google {"expireOn":"%s"}' % past: False,
            "user:ssh-rsa key google-ssh": False,
            "user:ssh-rsa key google-ssh {invalid:json}": False,
            'user:ssh-rsa key google-ssh {"userName":"user"}': False,
            'user:ssh-rsa key google-ssh {"expireOn":"invalid"}': False,
            'user:xyz key google-ssh {"expireOn":"%s"}' % future: False,
            'user:xyz key google-ssh {"expireOn":"%s"}' % past: True,
        }

        for key, expired in ssh_keys.items():
            self.assertEqual(DataSourceGCE._has_expired(key), expired)

    def test_parse_public_keys_non_ascii(self):
        public_key_data = [
            "cloudinit:rsa ssh-ke%s invalid" % chr(165),
            "use%sname:rsa ssh-key" % chr(174),
            "cloudinit:test 1",
            "default:test 2",
            "user:test 3",
        ]
        expected = ["test 1", "test 2"]
        found = DataSourceGCE._parse_public_keys(
            public_key_data, default_user="default"
        )
        self.assertEqual(sorted(found), sorted(expected))

    @mock.patch("cloudinit.url_helper.readurl")
    def test_publish_host_keys(self, m_readurl):
        hostkeys = [("ssh-rsa", "asdfasdf"), ("ssh-ed25519", "qwerqwer")]
        readurl_expected_calls = [
            mock.call(
                check_status=False,
                data=b"asdfasdf",
                headers=HEADERS,
                request_method="PUT",
                url="%s%s" % (GUEST_ATTRIBUTES_URL, "ssh-rsa"),
            ),
            mock.call(
                check_status=False,
                data=b"qwerqwer",
                headers=HEADERS,
                request_method="PUT",
                url="%s%s" % (GUEST_ATTRIBUTES_URL, "ssh-ed25519"),
            ),
        ]
        self.ds.publish_host_keys(hostkeys)
        m_readurl.assert_has_calls(readurl_expected_calls, any_order=True)

    @mock.patch(
        M_PATH + "EphemeralDHCPv4",
        autospec=True,
    )
    @mock.patch(M_PATH + "net.find_candidate_nics", return_value=["ens4"])
    def test_local_datasource_uses_ephemeral_dhcp(
        self, _m_find_candidate_nics, m_dhcp
    ):
        self._set_mock_metadata()
        distro = mock.MagicMock()
        distro.get_tmp_exec_path = self.tmp_dir
        ds = DataSourceGCE.DataSourceGCELocal(
            sys_cfg={}, distro=distro, paths=None
        )
        ds._get_data()
        assert m_dhcp.call_count == 1

    @mock.patch(M_PATH + "util.log_time")
    @mock.patch(
        M_PATH + "EphemeralDHCPv4",
        autospec=True,
    )
    @mock.patch(M_PATH + "net.find_candidate_nics")
    def test_local_datasource_tries_on_multi_nic(
        self, m_find_candidate_nics, m_dhcp, m_read_md
    ):
        self._set_mock_metadata()
        distro = mock.MagicMock()
        distro.get_tmp_exec_path = self.tmp_dir
        ds = DataSourceGCE.DataSourceGCELocal(
            sys_cfg={}, distro=distro, paths=None
        )
        m_find_candidate_nics.return_value = [
            "ens0p4",
            "ens0p5",
            "ens0p6",
            "ens4",
        ]
        m_dhcp.return_value.__enter__.side_effect = (
            None,
            NoDHCPLeaseError,
            None,
            None,
        )
        m_read_md.side_effect = (
            {"success": False},
            Exception("whoopsie, not this one"),
            {
                "success": True,
                "platform_reports_gce": True,
                "reason": "reason",
                "user-data": "ud",
                "meta-data": "md",
            },
        )
        assert ds._get_data() is True
        assert m_dhcp.call_args_list == [
            mock.call(distro, iface=DataSourceGCE.DEFAULT_PRIMARY_INTERFACE),
            mock.call(distro, iface="ens0p4"),
            mock.call(distro, iface="ens0p5"),
            mock.call(distro, iface="ens0p6"),
        ]
        assert ds.distro.fallback_interface == "ens0p6"
        assert ds.metadata == "md"
        assert ds.userdata_raw == "ud"

        expected_logs = (
            "Looking for the primary NIC in:"
            " ['ens4', 'ens0p4', 'ens0p5', 'ens0p6']",
            "Error fetching IMD with candidate NIC ens0p5:"
            " whoopsie, not this one",
        )
        for msg in expected_logs:
            self.assertIn(
                msg,
                self.logs.getvalue(),
            )

    @mock.patch(
        M_PATH + "EphemeralDHCPv4",
        autospec=True,
    )
    def test_datasource_doesnt_use_ephemeral_dhcp(self, m_dhcp):
        self._set_mock_metadata()
        ds = DataSourceGCE.DataSourceGCE(sys_cfg={}, distro=None, paths=None)
        ds._get_data()
        assert m_dhcp.call_count == 0
