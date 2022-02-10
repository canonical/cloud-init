# This file is part of cloud-init. See LICENSE file for license information.
"""A set of somewhat unrelated tests that can be combined into a single
instance launch. Generally tests should only be added here if a failure
of the test would be unlikely to affect the running of another test using
the same instance launch. Most independent module coherence tests can go
here.
"""
import json
import re

import pytest

from tests.integration_tests.clouds import ImageSpecification
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import (
    retry,
    verify_clean_log,
    verify_ordered_items_in_text,
)

USER_DATA = """\
#cloud-config
apt:
  primary:
    - arches: [default]
      uri: http://us.archive.ubuntu.com/ubuntu/
byobu_by_default: enable
final_message: |
  This is my final message!
  $version
  $timestamp
  $datasource
  $uptime
locale: en_GB.UTF-8
locale_configfile: /etc/default/locale
ntp:
  servers: ['ntp.ubuntu.com']
package_update: true
random_seed:
  data: 'MYUb34023nD:LFDK10913jk;dfnk:Df'
  encoding: raw
  file: /root/seed
rsyslog:
  configs:
    - "*.* @@127.0.0.1"
    - filename: 0-basic-config.conf
      content: |
        module(load="imtcp")
        input(type="imtcp" port="514")
        $template RemoteLogs,"/var/tmp/rsyslog.log"
        *.* ?RemoteLogs
        & ~
  remotes:
    me: "127.0.0.1"
runcmd:
  - echo 'hello world' > /var/tmp/runcmd_output

  - #
  - logger "My test log"
snap:
  squashfuse_in_container: true
  commands:
    - snap install hello-world
ssh_import_id:
  - gh:powersj
  - lp:smoser
timezone: US/Aleutian
"""


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
class TestCombined:
    def test_final_message(self, class_client: IntegrationInstance):
        """Test that final_message module works as expected.

        Also tests LP 1511485: final_message is silent.
        """
        client = class_client
        log = client.read_from_file("/var/log/cloud-init.log")
        expected = (
            "This is my final message!\n"
            r"\d+\.\d+.*\n"
            r"\w{3}, \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2} \+\d{4}\n"  # Datetime
            "DataSource.*\n"
            r"\d+\.\d+"
        )

        assert re.search(expected, log)

    def test_ntp_with_apt(self, class_client: IntegrationInstance):
        """LP #1628337.

        cloud-init tries to install NTP before even
        configuring the archives.
        """
        client = class_client
        log = client.read_from_file("/var/log/cloud-init.log")
        assert "W: Failed to fetch" not in log
        assert "W: Some index files failed to download" not in log
        assert "E: Unable to locate package ntp" not in log

    def test_byobu(self, class_client: IntegrationInstance):
        """Test byobu configured as enabled by default."""
        client = class_client
        assert client.execute('test -e "/etc/byobu/autolaunch"').ok

    def test_configured_locale(self, class_client: IntegrationInstance):
        """Test locale can be configured correctly."""
        client = class_client
        default_locale = client.read_from_file("/etc/default/locale")
        assert "LANG=en_GB.UTF-8" in default_locale

        locale_a = client.execute("locale -a")
        verify_ordered_items_in_text(["en_GB.utf8", "en_US.utf8"], locale_a)

        locale_gen = client.execute(
            "cat /etc/locale.gen | grep -v '^#' | uniq"
        )
        verify_ordered_items_in_text(
            ["en_GB.UTF-8", "en_US.UTF-8"], locale_gen
        )

    def test_random_seed_data(self, class_client: IntegrationInstance):
        """Integration test for the random seed module.

        This test specifies a command to be executed by the ``seed_random``
        module, by providing a different data to be used as seed data. We will
        then check if that seed data was actually used.
        """
        client = class_client

        # Only read the first 31 characters, because the rest could be
        # binary data
        result = client.execute("head -c 31 < /root/seed")
        assert result.startswith("MYUb34023nD:LFDK10913jk;dfnk:Df")

    def test_rsyslog(self, class_client: IntegrationInstance):
        """Test rsyslog is configured correctly."""
        client = class_client
        assert "My test log" in client.read_from_file("/var/tmp/rsyslog.log")

    def test_runcmd(self, class_client: IntegrationInstance):
        """Test runcmd works as expected"""
        client = class_client
        assert "hello world" == client.read_from_file("/var/tmp/runcmd_output")

    @retry(tries=30, delay=1)
    def test_ssh_import_id(self, class_client: IntegrationInstance):
        """Integration test for the ssh_import_id module.

        This test specifies ssh keys to be imported by the ``ssh_import_id``
        module and then checks that if the ssh keys were successfully imported.

        TODO:
        * This test assumes that SSH keys will be imported into the
        /home/ubuntu; this will need modification to run on other OSes.
        """
        client = class_client
        ssh_output = client.read_from_file("/home/ubuntu/.ssh/authorized_keys")

        assert "# ssh-import-id gh:powersj" in ssh_output
        assert "# ssh-import-id lp:smoser" in ssh_output

    def test_snap(self, class_client: IntegrationInstance):
        """Integration test for the snap module.

        This test specifies a command to be executed by the ``snap`` module
        and then checks that if that command was executed during boot.
        """
        client = class_client
        snap_output = client.execute("snap list")
        assert "core " in snap_output
        assert "hello-world " in snap_output

    def test_timezone(self, class_client: IntegrationInstance):
        """Integration test for the timezone module.

        This test specifies a timezone to be used by the ``timezone`` module
        and then checks that if that timezone was respected during boot.
        """
        client = class_client
        timezone_output = client.execute(
            'date "+%Z" --date="Thu, 03 Nov 2016 00:47:00 -0400"'
        )
        assert timezone_output.strip() == "HDT"

    def test_no_problems(self, class_client: IntegrationInstance):
        """Test no errors, warnings, or tracebacks"""
        client = class_client
        status_file = client.read_from_file("/run/cloud-init/status.json")
        status_json = json.loads(status_file)["v1"]
        for stage in ("init", "init-local", "modules-config", "modules-final"):
            assert status_json[stage]["errors"] == []
        result_file = client.read_from_file("/run/cloud-init/result.json")
        result_json = json.loads(result_file)["v1"]
        assert result_json["errors"] == []

        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)

    def test_correct_datasource_detected(
        self, class_client: IntegrationInstance
    ):
        """Test datasource is detected at the proper boot stage."""
        client = class_client
        status_file = client.read_from_file("/run/cloud-init/status.json")
        parsed_datasource = json.loads(status_file)["v1"]["datasource"]

        if client.settings.PLATFORM in ["lxd_container", "lxd_vm"]:
            assert parsed_datasource.startswith("DataSourceNoCloud")
        else:
            platform_datasources = {
                "azure": "DataSourceAzure [seed=/dev/sr0]",
                "ec2": "DataSourceEc2Local",
                "gce": "DataSourceGCELocal",
                "oci": "DataSourceOracle",
                "openstack": "DataSourceOpenStackLocal [net,ver=2]",
            }
            assert (
                platform_datasources[client.settings.PLATFORM]
                == parsed_datasource
            )

    def test_cloud_id_file_symlink(self, class_client: IntegrationInstance):
        cloud_id = class_client.execute("cloud-id").stdout
        expected_link_output = (
            "'/run/cloud-init/cloud-id' -> "
            f"'/run/cloud-init/cloud-id-{cloud_id}'"
        )
        assert expected_link_output == str(
            class_client.execute("stat -c %N /run/cloud-init/cloud-id")
        )

    def _check_common_metadata(self, data):
        assert data["base64_encoded_keys"] == []
        assert data["merged_cfg"] == "redacted for non-root user"

        image_spec = ImageSpecification.from_os_image()
        assert data["sys_info"]["dist"][0] == image_spec.os

        v1_data = data["v1"]
        assert re.match(r"\d\.\d+\.\d+-\d+", v1_data["kernel_release"])
        assert v1_data["variant"] == image_spec.os
        assert v1_data["distro"] == image_spec.os
        assert v1_data["distro_release"] == image_spec.release
        assert v1_data["machine"] == "x86_64"
        assert re.match(r"3.\d\.\d", v1_data["python_version"])

    @pytest.mark.lxd_container
    def test_instance_json_lxd(self, class_client: IntegrationInstance):
        client = class_client
        instance_json_file = client.read_from_file(
            "/run/cloud-init/instance-data.json"
        )

        data = json.loads(instance_json_file)
        self._check_common_metadata(data)
        v1_data = data["v1"]
        assert v1_data["cloud_name"] == "unknown"
        assert v1_data["platform"] == "lxd"
        assert v1_data["cloud_id"] == "lxd"
        assert f"{v1_data['cloud_id']}" == client.read_from_file(
            "/run/cloud-init/cloud-id-lxd"
        )
        assert (
            v1_data["subplatform"]
            == "seed-dir (/var/lib/cloud/seed/nocloud-net)"
        )
        assert v1_data["availability_zone"] is None
        assert v1_data["instance_id"] == client.instance.name
        assert v1_data["local_hostname"] == client.instance.name
        assert v1_data["region"] is None

    @pytest.mark.lxd_vm
    def test_instance_json_lxd_vm(self, class_client: IntegrationInstance):
        client = class_client
        instance_json_file = client.read_from_file(
            "/run/cloud-init/instance-data.json"
        )

        data = json.loads(instance_json_file)
        self._check_common_metadata(data)
        v1_data = data["v1"]
        assert v1_data["cloud_name"] == "unknown"
        assert v1_data["platform"] == "lxd"
        assert v1_data["cloud_id"] == "lxd"
        assert f"{v1_data['cloud_id']}" == client.read_from_file(
            "/run/cloud-init/cloud-id-lxd"
        )
        assert any(
            [
                "/var/lib/cloud/seed/nocloud-net" in v1_data["subplatform"],
                "/dev/sr0" in v1_data["subplatform"],
            ]
        )
        assert v1_data["availability_zone"] is None
        assert v1_data["instance_id"] == client.instance.name
        assert v1_data["local_hostname"] == client.instance.name
        assert v1_data["region"] is None

    @pytest.mark.ec2
    def test_instance_json_ec2(self, class_client: IntegrationInstance):
        client = class_client
        instance_json_file = client.read_from_file(
            "/run/cloud-init/instance-data.json"
        )
        data = json.loads(instance_json_file)
        v1_data = data["v1"]
        assert v1_data["cloud_name"] == "aws"
        assert v1_data["platform"] == "ec2"
        # Different regions will show up as ec2-(gov|china)
        assert v1_data["cloud_id"].startswith("ec2")
        assert f"{v1_data['cloud_id']}" == client.read_from_file(
            "/run/cloud-init/cloud-id-ec2"
        )
        assert v1_data["subplatform"].startswith("metadata")
        assert (
            v1_data["availability_zone"] == client.instance.availability_zone
        )
        assert v1_data["instance_id"] == client.instance.name
        assert v1_data["local_hostname"].startswith("ip-")
        assert v1_data["region"] == client.cloud.cloud_instance.region

    @pytest.mark.gce
    def test_instance_json_gce(self, class_client: IntegrationInstance):
        client = class_client
        instance_json_file = client.read_from_file(
            "/run/cloud-init/instance-data.json"
        )
        data = json.loads(instance_json_file)
        self._check_common_metadata(data)
        v1_data = data["v1"]
        assert v1_data["cloud_name"] == "gce"
        assert v1_data["platform"] == "gce"
        assert f"{v1_data['cloud_id']}" == client.read_from_file(
            "/run/cloud-init/cloud-id-gce"
        )
        assert v1_data["subplatform"].startswith("metadata")
        assert v1_data["availability_zone"] == client.instance.zone
        assert v1_data["instance_id"] == client.instance.instance_id
        assert v1_data["local_hostname"] == client.instance.name
