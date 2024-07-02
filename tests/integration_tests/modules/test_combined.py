# This file is part of cloud-init. See LICENSE file for license information.
"""A set of somewhat unrelated tests that can be combined into a single
instance launch. Generally tests should only be added here if a failure
of the test would be unlikely to affect the running of another test using
the same instance launch. Most independent module coherence tests can go
here.
"""
import glob
import importlib
import json
import re
import uuid
from pathlib import Path

import pytest
from pycloudlib.ec2.instance import EC2Instance
from pycloudlib.gce.instance import GceInstance

import cloudinit.config
from cloudinit.util import is_true, should_log_deprecation
from tests.integration_tests.decorators import retry
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, IS_UBUNTU, MANTIC
from tests.integration_tests.util import (
    get_feature_flag_value,
    get_inactive_modules,
    lxd_has_nocloud,
    verify_clean_log,
    verify_ordered_items_in_text,
)

USER_DATA = """\
#cloud-config
users:
- default
- name: craig
  sudo: false  # make sure craig doesn't get elevated perms
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
        $template RemoteLogs,"/var/spool/rsyslog/cloudinit.log"
        *.* ?RemoteLogs
        & ~
  remotes:
    me: "127.0.0.1"
runcmd:
  - echo 'hello world' > /var/tmp/runcmd_output
  - echo '💩' > /var/tmp/unicode_data

  - #
  - logger "My test log"
snap:
  commands:
    - snap install hello-world
ssh_import_id:
  - lp:smoser

timezone: Europe/Madrid
"""


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
class TestCombined:
    @pytest.mark.skipif(not IS_UBUNTU, reason="Uses netplan")
    def test_netplan_permissions(self, class_client: IntegrationInstance):
        """
        Test that netplan config file is generated with proper permissions
        """
        log = class_client.read_from_file("/var/log/cloud-init.log")
        if CURRENT_RELEASE < MANTIC:
            assert (
                "No netplan python module. Fallback to write"
                " /etc/netplan/50-cloud-init.yaml" in log
            )
        else:
            assert "Rendered netplan config using netplan python API" in log
        file_perms = class_client.execute(
            "stat -c %a /etc/netplan/50-cloud-init.yaml"
        )
        assert file_perms.ok, "Unable to check perms on 50-cloud-init.yaml"
        feature_netplan_root_only = is_true(
            get_feature_flag_value(
                class_client, "NETPLAN_CONFIG_ROOT_READ_ONLY"
            )
        )
        config_perms = "600" if feature_netplan_root_only else "644"
        assert config_perms == file_perms.stdout.strip()

    def test_final_message(self, class_client: IntegrationInstance):
        """Test that final_message module works as expected.

        Also tests LP 1511485: final_message is silent.
        """
        client = class_client
        log = client.read_from_file("/var/log/cloud-init.log")
        expected = (
            "This is my final message!\n"
            r"\d+\.(\d+|daily).*\n"
            r"\w{3}, \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2} \+\d{4}\n"  # Datetime
            "DataSource.*\n"
            r"\d+\.\d+"
        )

        assert re.search(expected, log)

    def test_deprecated_message(self, class_client: IntegrationInstance):
        """Check that deprecated key produces a log warning"""
        client = class_client
        log = client.read_from_file("/var/log/cloud-init.log")
        version_boundary = get_feature_flag_value(
            class_client, "DEPRECATION_INFO_BOUNDARY"
        )
        # the deprecation_version is 22.2 in schema for apt_* keys in
        # user-data. Pass 22.2 in against the client's version_boundary.
        if should_log_deprecation("22.2", version_boundary):
            log_level = "DEPRECATED"
        else:
            log_level = "INFO"

        assert (
            f"[{log_level}]: The value of 'false' in user craig's 'sudo'"
            " config is deprecated" in log
        )
        assert 2 == log.count("DEPRECATE")

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
        assert "My test log" in client.read_from_file(
            "/var/spool/rsyslog/cloudinit.log"
        )

    def test_runcmd(self, class_client: IntegrationInstance):
        """Test runcmd works as expected"""
        client = class_client
        assert "hello world" == client.read_from_file("/var/tmp/runcmd_output")

    def test_snap(self, class_client: IntegrationInstance):
        """Integration test for the snap module.

        This test verify that the snap packages specified in the user-data
        were installed by the ``snap`` module during boot.
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
        assert timezone_output.strip() == "CET"

    def test_no_problems(self, class_client: IntegrationInstance):
        """Test no errors, warnings, deprecations, tracebacks or
        inactive modules.
        """
        client = class_client
        status_file = client.read_from_file("/run/cloud-init/status.json")
        status_json = json.loads(status_file)["v1"]
        for stage in ("init", "init-local", "modules-config", "modules-final"):
            assert status_json[stage]["errors"] == []
        result_file = client.read_from_file("/run/cloud-init/result.json")
        result_json = json.loads(result_file)["v1"]
        assert result_json["errors"] == []

        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log, ignore_deprecations=False)
        requested_modules = {
            "apt_configure",
            "byobu",
            "final_message",
            "locale",
            "ntp",
            "seed_random",
            "rsyslog",
            "runcmd",
            "snap",
            "ssh_import_id",
            "timezone",
        }
        inactive_modules = get_inactive_modules(log)
        assert not requested_modules.intersection(inactive_modules), (
            f"Expected active modules:"
            f" {requested_modules.intersection(inactive_modules)}"
        )

    def test_correct_datasource_detected(
        self, class_client: IntegrationInstance
    ):
        """Test datasource is detected at the proper boot stage."""
        client = class_client
        status_file = client.read_from_file("/run/cloud-init/status.json")
        parsed_datasource = json.loads(status_file)["v1"]["datasource"]

        if client.settings.PLATFORM in ["lxd_container", "lxd_vm"]:
            if lxd_has_nocloud(client):
                datasource = "DataSourceNoCloud"
            else:
                datasource = "DataSourceLXD"
            assert parsed_datasource.startswith(datasource)
        else:
            platform_datasources = {
                "azure": "DataSourceAzure [seed=/dev/sr0]",
                "ec2": "DataSourceEc2Local",
                "gce": "DataSourceGCELocal",
                "oci": "DataSourceOracle",
                "openstack": "DataSourceOpenStackLocal [net,ver=2]",
                "qemu": "DataSourceNoCloud [seed=/dev/vda][dsmode=net]",
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

    def test_run_frequency(self, class_client: IntegrationInstance):
        log = class_client.read_from_file("/var/log/cloud-init.log")
        config_dir = Path(cloudinit.config.__file__).parent
        module_paths = glob.glob(str(config_dir / "cc*.py"))
        module_names = [Path(x).stem for x in module_paths]
        found_count = 0
        for name in module_names:
            mod = importlib.import_module(f"cloudinit.config.{name}")
            frequency = mod.meta["frequency"]
            # cc_ gets replaced with config- in logs
            log_name = name.replace("cc_", "config-")
            # Some modules have been filtered out in /etc/cloud/cloud.cfg,
            if f"running {log_name}" in log:
                found_count += 1  # Ensure we're matching on the right text
                assert f"running {log_name} with frequency {frequency}" in log
        assert (
            found_count > 10
        ), "Not enough modules found in log. Did the log message change?"
        assert "with frequency None" not in log

    def _check_common_metadata(self, data):
        assert data["base64_encoded_keys"] == []
        assert data["merged_cfg"] == "redacted for non-root user"

        assert data["sys_info"]["dist"][0] == CURRENT_RELEASE.os

        v1_data = data["v1"]
        assert v1_data["variant"] == CURRENT_RELEASE.os
        assert v1_data["distro"] == CURRENT_RELEASE.os
        assert v1_data["distro_release"] == CURRENT_RELEASE.series
        assert v1_data["machine"] == "x86_64"
        assert re.match(r"3.\d+\.\d+", v1_data["python_version"])

    @pytest.mark.skipif(not IS_UBUNTU, reason="Testing default_user ubuntu")
    def test_combined_cloud_config_json(
        self, class_client: IntegrationInstance
    ):
        client = class_client
        combined_json = client.read_from_file(
            "/run/cloud-init/combined-cloud-config.json"
        )
        data = json.loads(combined_json)
        expected_features = json.loads(
            client.execute(
                "python3 -c 'import json; from cloudinit import features; "
                "print(json.dumps(features.get_features()))'"
            )
        )
        assert data["features"] == expected_features
        assert data["system_info"]["default_user"]["name"] == "ubuntu"

    @pytest.mark.skipif(
        PLATFORM not in ("lxd_vm", "lxd_container"),
        reason="Test is LXD specific",
    )
    def test_network_config_json(self, class_client: IntegrationInstance):
        client = class_client
        network_json = client.read_from_file(
            "/run/cloud-init/network-config.json"
        )
        devname = "eth0" if PLATFORM == "lxd_container" else "enp5s0"
        assert {
            "config": [
                {
                    "name": devname,
                    "subnets": [{"control": "auto", "type": "dhcp"}],
                    "type": "physical",
                }
            ],
            "version": 1,
        } == json.loads(network_json)

    @pytest.mark.skipif(
        PLATFORM != "lxd_container",
        reason="Test is LXD container specific",
    )
    def test_instance_json_lxd(self, class_client: IntegrationInstance):
        client = class_client
        instance_json_file = client.read_from_file(
            "/run/cloud-init/instance-data.json"
        )

        data = json.loads(instance_json_file)
        self._check_common_metadata(data)
        v1_data = data["v1"]
        if not lxd_has_nocloud(client):
            cloud_name = "lxd"
            subplatform = "LXD socket API v. 1.0 (/dev/lxd/sock)"
            # instance-id should be a UUID
            try:
                uuid.UUID(v1_data["instance_id"])
            except ValueError:
                raise AssertionError(
                    f"LXD instance-id is not a UUID: {v1_data['instance_id']}"
                )
        else:
            cloud_name = "unknown"
            subplatform = "seed-dir (/var/lib/cloud/seed/nocloud-net)"
            # Pre-Jammy instance-id and instance.name are synonymous
            assert v1_data["instance_id"] == client.instance.name
        assert v1_data["cloud_name"] == cloud_name
        assert v1_data["subplatform"] == subplatform
        assert v1_data["platform"] == "lxd"
        assert v1_data["cloud_id"] == "lxd"
        assert f"{v1_data['cloud_id']}" == client.read_from_file(
            "/run/cloud-init/cloud-id-lxd"
        )
        assert v1_data["availability_zone"] is None
        assert v1_data["local_hostname"] == client.instance.name
        assert v1_data["region"] is None

    @pytest.mark.skipif(PLATFORM != "lxd_vm", reason="Test is LXD VM specific")
    def test_instance_json_lxd_vm(self, class_client: IntegrationInstance):
        client = class_client
        instance_json_file = client.read_from_file(
            "/run/cloud-init/instance-data.json"
        )

        data = json.loads(instance_json_file)
        self._check_common_metadata(data)
        v1_data = data["v1"]
        if not lxd_has_nocloud(client):
            cloud_name = "lxd"
            subplatform = "LXD socket API v. 1.0 (/dev/lxd/sock)"
            # instance-id should be a UUID
            try:
                uuid.UUID(v1_data["instance_id"])
            except ValueError as e:
                raise AssertionError(
                    f"LXD instance-id is not a UUID: {v1_data['instance_id']}"
                ) from e
            assert v1_data["subplatform"] == subplatform
            assert v1_data["platform"] == "lxd"
            assert v1_data["cloud_id"] == "lxd"
        else:
            cloud_name = "unknown"
            # Pre-Jammy instance-id and instance.name are synonymous
            assert v1_data["instance_id"] == client.instance.name
            assert any(
                [
                    "/var/lib/cloud/seed/nocloud-net"
                    in v1_data["subplatform"],
                    "/dev/sr0" in v1_data["subplatform"],
                ]
            )
            assert v1_data["platform"] in ["lxd", "nocloud"]
            assert v1_data["cloud_id"] in ["lxd", "nocloud"]
        assert v1_data["cloud_name"] == cloud_name
        assert f"{v1_data['cloud_id']}" == client.read_from_file(
            "/run/cloud-init/cloud-id"
        )

        assert v1_data["availability_zone"] is None
        assert v1_data["local_hostname"] == client.instance.name
        assert v1_data["region"] is None

    @pytest.mark.skipif(PLATFORM != "ec2", reason="Test is ec2 specific")
    def test_instance_json_ec2(self, class_client: IntegrationInstance):
        client = class_client
        instance_json_file = client.read_from_file(
            "/run/cloud-init/instance-data.json"
        )
        data = json.loads(instance_json_file)
        v1_data = data["v1"]
        assert v1_data["cloud_name"] == "aws"
        assert v1_data["platform"] == "ec2"
        # Different regions will show up as aws-(gov|china)
        assert v1_data["cloud_id"].startswith("aws")
        assert f"{v1_data['cloud_id']}" == client.read_from_file(
            "/run/cloud-init/cloud-id-aws"
        )
        assert v1_data["subplatform"].startswith("metadata")

        # type narrow since availability_zone is not a BaseInstance attribute
        assert isinstance(client.instance, EC2Instance)
        assert (
            v1_data["availability_zone"] == client.instance.availability_zone
        )
        assert v1_data["instance_id"] == client.instance.name
        assert v1_data["local_hostname"].startswith("ip-")
        assert v1_data["region"] == client.cloud.cloud_instance.region

    @pytest.mark.skipif(PLATFORM != "gce", reason="Test is GCE specific")
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
        # type narrow since zone and instance_id are not BaseInstance
        # attributes
        assert isinstance(client.instance, GceInstance)
        assert v1_data["availability_zone"] == client.instance.zone
        assert v1_data["instance_id"] == client.instance.instance_id
        assert v1_data["local_hostname"] == client.instance.name

    @pytest.mark.skipif(
        PLATFORM not in ["lxd_container", "azure", "gce", "ec2"],
        reason=(
            f"Test was written for {PLATFORM} but can likely run on "
            "other platforms."
        ),
    )
    def test_instance_cloud_id_across_reboot(
        self, class_client: IntegrationInstance
    ):
        client = class_client
        platform = client.settings.PLATFORM
        cloud_id_alias = {"ec2": "aws", "lxd_container": "lxd"}
        cloud_file = f"cloud-id-{cloud_id_alias.get(platform, platform)}"
        assert client.execute(f"test -f /run/cloud-init/{cloud_file}").ok
        assert client.execute("test -f /run/cloud-init/cloud-id").ok
        client.restart()
        assert client.execute(f"test -f /run/cloud-init/{cloud_file}").ok
        assert client.execute("test -f /run/cloud-init/cloud-id").ok

    def test_unicode(self, class_client: IntegrationInstance):
        client = class_client
        assert "💩" == client.read_from_file("/var/tmp/unicode_data")


@pytest.mark.user_data(USER_DATA)
class TestCombinedNoCI:
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

        assert "# ssh-import-id lp:smoser" in ssh_output
