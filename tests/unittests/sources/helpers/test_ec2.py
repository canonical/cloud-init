# This file is part of cloud-init. See LICENSE file for license information.

import responses

from cloudinit import url_helper as uh
from cloudinit.sources.helpers import ec2
from cloudinit.sources.helpers.ec2 import get_primary_mac_from_metadata


class TestGetPrimaryMacFromMetadata:
    def test_no_metadata(self):
        assert get_primary_mac_from_metadata(None) is None

    def test_empty_metadata(self):
        assert get_primary_mac_from_metadata({}) is None

    def test_no_network_section(self):
        md = {"foo": "bar"}
        assert get_primary_mac_from_metadata(md) is None

    def test_single_primary_nic(self):
        md = {
            "network": {
                "interfaces": {
                    "macs": {
                        "aa:bb:cc:dd:ee:ff": {
                            "network-card": "0",
                            "device-number": "0",
                        },
                        "11:22:33:44:55:66": {
                            "network-card": "1",
                            "device-number": "0",
                        },
                    }
                }
            }
        }

        assert get_primary_mac_from_metadata(md) == "aa:bb:cc:dd:ee:ff"

    def test_primary_not_first_in_dict(self):
        md = {
            "network": {
                "interfaces": {
                    "macs": {
                        "11:22:33:44:55:66": {
                            "network-card": "1",
                            "device-number": "0",
                        },
                        "aa:bb:cc:dd:ee:ff": {
                            "network-card": "0",
                            "device-number": "0",
                        },
                    }
                }
            }
        }

        assert get_primary_mac_from_metadata(md) == "aa:bb:cc:dd:ee:ff"

    def test_multiple_primary_candidates(self):
        md = {
            "network": {
                "interfaces": {
                    "macs": {
                        "bb:bb:bb:bb:bb:bb": {
                            "network-card": "0",
                            "device-number": "0",
                        },
                        "aa:aa:aa:aa:aa:aa": {
                            "network-card": "0",
                            "device-number": "0",
                        },
                    }
                }
            }
        }

        # Deterministic: lowest lexicographically
        assert get_primary_mac_from_metadata(md) == "aa:aa:aa:aa:aa:aa"

    def test_invalid_values_are_ignored(self):
        md = {
            "network": {
                "interfaces": {
                    "macs": {
                        "aa:bb": {
                            "network-card": "foo",
                            "device-number": "bar",
                        }
                    }
                }
            }
        }

        assert get_primary_mac_from_metadata(md) is None


class TestEc2Util:
    VERSION = "latest"

    @responses.activate
    def test_userdata_fetch(self):
        responses.add(
            responses.GET,
            "http://169.254.169.254/%s/user-data" % (self.VERSION),
            body="stuff",
            status=200,
        )
        userdata = ec2.get_instance_userdata(self.VERSION)
        assert "stuff" == userdata.decode("utf-8")

    @responses.activate
    def test_userdata_fetch_fail_not_found(self):
        responses.add(
            responses.GET,
            "http://169.254.169.254/%s/user-data" % (self.VERSION),
            status=404,
        )
        userdata = ec2.get_instance_userdata(self.VERSION, retries=0)
        assert b"" == userdata

    @responses.activate
    def test_userdata_fetch_fail_server_dead(self):
        responses.add(
            responses.GET,
            "http://169.254.169.254/%s/user-data" % (self.VERSION),
            status=500,
        )
        userdata = ec2.get_instance_userdata(self.VERSION, retries=0)
        assert b"" == userdata

    @responses.activate
    def test_userdata_fetch_fail_server_not_found(self):
        responses.add(
            responses.GET,
            "http://169.254.169.254/%s/user-data" % (self.VERSION),
            status=404,
        )
        userdata = ec2.get_instance_userdata(self.VERSION)
        assert b"" == userdata

    @responses.activate
    def test_metadata_fetch_no_keys(self):
        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(["hostname", "instance-id", "ami-launch-index"]),
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "hostname"),
            status=200,
            body="ec2.fake.host.name.com",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "instance-id"),
            status=200,
            body="123",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "ami-launch-index"),
            status=200,
            body="1",
        )
        md = ec2.get_instance_metadata(self.VERSION, retries=0)
        assert md["hostname"] == "ec2.fake.host.name.com"
        assert md["instance-id"] == "123"
        assert md["ami-launch-index"] == "1"

    @responses.activate
    def test_metadata_fetch_key(self):
        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(["hostname", "instance-id", "public-keys/"]),
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "hostname"),
            status=200,
            body="ec2.fake.host.name.com",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "instance-id"),
            status=200,
            body="123",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "public-keys/"),
            status=200,
            body="0=my-public-key",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "public-keys/0/openssh-key"),
            status=200,
            body="ssh-rsa AAAA.....wZEf my-public-key",
        )
        md = ec2.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        assert md["hostname"] == "ec2.fake.host.name.com"
        assert md["instance-id"] == "123"
        assert 1 == len(md["public-keys"])

    @responses.activate
    def test_metadata_fetch_with_2_keys(self):
        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(["hostname", "instance-id", "public-keys/"]),
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "hostname"),
            status=200,
            body="ec2.fake.host.name.com",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "instance-id"),
            status=200,
            body="123",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "public-keys/"),
            status=200,
            body="\n".join(["0=my-public-key", "1=my-other-key"]),
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "public-keys/0/openssh-key"),
            status=200,
            body="ssh-rsa AAAA.....wZEf my-public-key",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "public-keys/1/openssh-key"),
            status=200,
            body="ssh-rsa AAAA.....wZEf my-other-key",
        )
        md = ec2.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        assert md["hostname"] == "ec2.fake.host.name.com"
        assert md["instance-id"] == "123"
        assert 2 == len(md["public-keys"])

    @responses.activate
    def test_metadata_fetch_bdm(self):
        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(
                ["hostname", "instance-id", "block-device-mapping/"]
            ),
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "hostname"),
            status=200,
            body="ec2.fake.host.name.com",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "instance-id"),
            status=200,
            body="123",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "block-device-mapping/"),
            status=200,
            body="\n".join(["ami", "ephemeral0"]),
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "block-device-mapping/ami"),
            status=200,
            body="sdb",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "block-device-mapping/ephemeral0"),
            status=200,
            body="sdc",
        )
        md = ec2.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        assert md["hostname"] == "ec2.fake.host.name.com"
        assert md["instance-id"] == "123"
        bdm = md["block-device-mapping"]
        assert 2 == len(bdm)
        assert bdm["ami"] == "sdb"
        assert bdm["ephemeral0"] == "sdc"

    @responses.activate
    def test_metadata_no_security_credentials(self):
        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(["instance-id", "iam/"]),
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "instance-id"),
            status=200,
            body="i-0123451689abcdef0",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "iam/"),
            status=200,
            body="\n".join(["info/", "security-credentials/"]),
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "iam/info/"),
            status=200,
            body="LastUpdated",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "iam/info/LastUpdated"),
            status=200,
            body="2016-10-27T17:29:39Z",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "iam/security-credentials/"),
            status=200,
            body="ReadOnly/",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "iam/security-credentials/ReadOnly/"),
            status=200,
            body="\n".join(["LastUpdated", "Expiration"]),
        )
        responses.add(
            responses.GET,
            uh.combine_url(
                base_url, "iam/security-credentials/ReadOnly/LastUpdated"
            ),
            status=200,
            body="2016-10-27T17:28:17Z",
        )
        responses.add(
            responses.GET,
            uh.combine_url(
                base_url, "iam/security-credentials/ReadOnly/Expiration"
            ),
            status=200,
            body="2016-10-28T00:00:34Z",
        )
        md = ec2.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        assert md["instance-id"] == "i-0123451689abcdef0"
        iam = md["iam"]
        assert 1 == len(iam)
        assert iam["info"]["LastUpdated"] == "2016-10-27T17:29:39Z"
        assert "security-credentials" not in iam

    @responses.activate
    def test_metadata_children_with_invalid_character(self):
        def _skip_tags(exception):
            if isinstance(exception, uh.UrlError) and exception.code == 404:
                if exception.url and "meta-data/tags/" in exception.url:
                    print(exception.url)
                    return True
            return False

        base_url = "http://169.254.169.254/%s/meta-data/" % (self.VERSION)
        responses.add(
            responses.GET,
            base_url,
            status=200,
            body="\n".join(["tags/", "ami-launch-index"]),
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "tags/"),
            status=200,
            body="\n".join(["test/invalid", "valid"]),
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "tags/valid"),
            status=200,
            body="OK",
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "tags/test/invalid"),
            status=404,
        )
        responses.add(
            responses.GET,
            uh.combine_url(base_url, "ami-launch-index"),
            status=200,
            body="1",
        )
        md = ec2.get_instance_metadata(
            self.VERSION,
            retries=0,
            timeout=0.1,
            retrieval_exception_ignore_cb=_skip_tags,
        )
        assert md["tags"]["valid"] == "OK"
        assert md["tags"]["test/invalid"] == "(skipped)"
        assert md["ami-launch-index"] == "1"
        md = ec2.get_instance_metadata(self.VERSION, retries=0, timeout=0.1)
        assert len(md) == 0
