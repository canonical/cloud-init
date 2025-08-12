# This file is part of cloud-init. See LICENSE file for license information.

import json
import os
import re

import pytest
import responses

from cloudinit import util
from cloudinit.config import cc_chef
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.helpers import cloud_init_project_dir
from tests.unittests.helpers import (
    SCHEMA_EMPTY_ERROR,
    mock,
    skipIf,
    skipUnlessJsonSchema,
)
from tests.unittests.util import MockDistro, get_cloud

try:
    client_path = cloud_init_project_dir("templates/chef_client.rb.tmpl")
    with open(client_path) as stream:
        CLIENT_TEMPL = stream.read()
except FileNotFoundError:
    CLIENT_TEMPL = ""


class TestInstallChefOmnibus:

    @responses.activate
    @mock.patch("cloudinit.config.cc_chef.OMNIBUS_URL", cc_chef.OMNIBUS_URL)
    def test_install_chef_from_omnibus_runs_chef_url_content(self):
        """install_chef_from_omnibus calls subp_blob_in_tempfile."""
        response = b'#!/bin/bash\necho "Hi Mom"'
        responses.add(
            responses.GET, cc_chef.OMNIBUS_URL, body=response, status=200
        )
        ret = (None, None)  # stdout, stderr but capture=False
        distro = mock.Mock()

        with mock.patch(
            "cloudinit.config.cc_chef.subp_blob_in_tempfile", return_value=ret
        ) as m_subp_blob:
            cc_chef.install_chef_from_omnibus(distro=distro)
        # admittedly whitebox, but assuming subp_blob_in_tempfile works
        # this should be fine.
        assert [
            mock.call(
                blob=response,
                args=[],
                basename="chef-omnibus-install",
                capture=False,
                distro=distro,
            )
        ] == m_subp_blob.call_args_list

    @mock.patch("cloudinit.config.cc_chef.url_helper.readurl")
    @mock.patch("cloudinit.config.cc_chef.subp_blob_in_tempfile")
    def test_install_chef_from_omnibus_retries_url(
        self, m_subp_blob, m_rdurl, tmpdir
    ):
        """install_chef_from_omnibus retries OMNIBUS_URL upon failure."""

        class FakeURLResponse:
            contents = f'#!/bin/bash\necho "Hi Mom" > {tmpdir}/chef.out'

        m_rdurl.return_value = FakeURLResponse()

        distro = mock.Mock()
        cc_chef.install_chef_from_omnibus(distro=distro)
        expected_kwargs = {
            "retries": cc_chef.OMNIBUS_URL_RETRIES,
            "url": cc_chef.OMNIBUS_URL,
        }
        assert expected_kwargs == m_rdurl.call_args_list[0][1]
        cc_chef.install_chef_from_omnibus(retries=10, distro=distro)
        expected_kwargs = {"retries": 10, "url": cc_chef.OMNIBUS_URL}
        cc_chef.install_chef_from_omnibus(
            retries=10, distro=distro, omnibus_version="2.0"
        )
        assert expected_kwargs == m_rdurl.call_args_list[1][1]
        expected_subp_kwargs = {
            "args": ["-v", "2.0"],
            "basename": "chef-omnibus-install",
            "blob": m_rdurl.return_value.contents,
            "capture": False,
            "distro": distro,
        }
        assert expected_subp_kwargs == m_subp_blob.call_args_list[2][1]

    @responses.activate
    @mock.patch("cloudinit.config.cc_chef.OMNIBUS_URL", cc_chef.OMNIBUS_URL)
    @mock.patch("cloudinit.config.cc_chef.subp_blob_in_tempfile")
    def test_install_chef_from_omnibus_has_omnibus_version(
        self, m_subp_blob, tmpdir
    ):
        """install_chef_from_omnibus provides version arg to OMNIBUS_URL."""
        chef_outfile = tmpdir / "chef.out"
        response = '#!/bin/bash\necho "Hi Mom" > {0}'.format(chef_outfile)
        responses.add(responses.GET, cc_chef.OMNIBUS_URL, body=response)
        distro = mock.Mock()
        cc_chef.install_chef_from_omnibus(distro=distro, omnibus_version="2.0")

        called_kwargs = m_subp_blob.call_args_list[0][1]
        expected_kwargs = {
            "args": ["-v", "2.0"],
            "basename": "chef-omnibus-install",
            "blob": response.encode("utf-8"),
            "capture": False,
            "distro": distro,
        }
        assert expected_kwargs == called_kwargs


@pytest.mark.usefixtures("fake_filesystem")
class TestChef:

    def test_no_config(self):
        """No chef directories are created on when no chef config provided"""
        cfg = {}
        cc_chef.handle("chef", cfg, get_cloud(), [])
        for d in cc_chef.CHEF_DIRS:
            assert not os.path.isdir(d)

    @skipIf(not CLIENT_TEMPL, "templates/chef_client.rb.tmpl is not available")
    def test_basic_config(self):
        """
        test basic config looks correct

        # This should create a file of the format...
        # Created by cloud-init v. 0.7.6 on Sat, 11 Oct 2014 23:57:21 +0000
        chef_license           "accept"
        log_level              :info
        ssl_verify_mode        :verify_none
        log_location           "/var/log/chef/client.log"
        validation_client_name "bob"
        validation_key         "/etc/chef/validation.pem"
        client_key             "/etc/chef/client.pem"
        chef_server_url        "localhost"
        environment            "_default"
        node_name              "iid-datasource-none"
        json_attribs           "/etc/chef/firstboot.json"
        file_cache_path        "/var/chef/cache"
        file_backup_path       "/var/chef/backup"
        pid_file               "/var/run/chef/client.pid"
        Chef::Log::Formatter.show_time = true
        encrypted_data_bag_secret  "/etc/chef/encrypted_data_bag_secret"
        """
        util.write_file(
            "/etc/cloud/templates/chef_client.rb.tmpl", CLIENT_TEMPL
        )
        cfg = {
            "chef": {
                "chef_license": "accept",
                "server_url": "localhost",
                "validation_name": "bob",
                "validation_key": "/etc/chef/vkey.pem",
                "validation_cert": "this is my cert",
                "encrypted_data_bag_secret": (
                    "/etc/chef/encrypted_data_bag_secret"
                ),
            },
        }
        cc_chef.handle("chef", cfg, get_cloud(), [])
        for d in cc_chef.CHEF_DIRS:
            assert os.path.isdir(d)
        c = util.load_text_file(cc_chef.CHEF_RB_PATH)

        # the content of these keys is not expected to be rendered to tmpl
        unrendered_keys = ("validation_cert",)
        for k, v in cfg["chef"].items():
            if k in unrendered_keys:
                continue
            assert v in c
        for k, v in cc_chef.CHEF_RB_TPL_DEFAULTS.items():
            if k in unrendered_keys:
                continue
            # the value from the cfg overrides that in the default
            val = cfg["chef"].get(k, v)
            if isinstance(val, str):
                assert val in c
        c = util.load_text_file(cc_chef.CHEF_FB_PATH)
        assert {} == json.loads(c)

    def test_firstboot_json(self):
        cfg = {
            "chef": {
                "server_url": "localhost",
                "validation_name": "bob",
                "run_list": ["a", "b", "c"],
                "initial_attributes": {
                    "c": "d",
                },
            },
        }
        cc_chef.handle("chef", cfg, get_cloud(), [])
        c = util.load_text_file(cc_chef.CHEF_FB_PATH)
        assert {
            "run_list": ["a", "b", "c"],
            "c": "d",
        } == json.loads(c)

    @pytest.mark.parametrize(
        "file_content, shutil_moves, expected_msg_count",
        (
            pytest.param({}, [], {}, id="no_migration_when_dirs_empty"),
            pytest.param(
                {"/var/cache/chef/cache.1": "cache1"},
                [mock.call("/var/cache/chef/cache.1", "/var/chef/cache")],
                {"Moving /var/cache/chef/cache.1 to /var/chef/cache": 1},
                id="migration_when_old_cache_dir_present",
            ),
            pytest.param(
                {"/var/backups/chef/backup.1": "backup1"},
                [mock.call("/var/backups/chef/backup.1", "/var/chef/backup")],
                {"Moving /var/backups/chef/backup.1 to /var/chef/backup": 1},
                id="migration_when_old_backups_dir_present",
            ),
            pytest.param(
                {
                    "/var/backups/chef/backup.1": "backup1",
                    "/var/chef/backup/backup.1": "backup1",
                },
                [],
                {
                    "Ignoring migration of /var/backups/chef/backup.1."
                    " File already exists in /var/chef/backup": 1
                },
                id="migration_skips_when_migrated_file_present",
            ),
        ),
    )
    def test_migrate_chef_config_dirs(
        self, file_content, shutil_moves, expected_msg_count, caplog
    ):
        """When present, old backup and cache dirs migrated to defaults"""
        cfg = {
            "chef": {
                "server_url": "localhost",
                "validation_name": "bob",
                "run_list": ["a", "b", "c"],
                "initial_attributes": {
                    "c": "d",
                },
            },
        }
        for file_path in file_content:
            util.ensure_dir(os.path.dirname(file_path))
            util.write_file(file_path, file_content[file_path])
        util.write_file(
            "/etc/cloud/templates/chef_client.rb.tmpl", CLIENT_TEMPL
        )
        with mock.patch("cloudinit.config.cc_chef.shutil.move") as m_shutil:
            cc_chef.handle("chef", cfg, get_cloud(), [])
        assert m_shutil.call_args_list == shutil_moves
        if len(file_content) == 0:
            # no files to migrate, so we don't expect any messages
            assert "Moving" not in caplog.text
        for expected_msg, count in expected_msg_count.items():
            assert caplog.text.count(expected_msg) == count

    @skipIf(not CLIENT_TEMPL, "templates/chef_client.rb.tmpl is not available")
    def test_template_deletes(self):

        util.write_file(
            "/etc/cloud/templates/chef_client.rb.tmpl", CLIENT_TEMPL
        )
        cfg = {
            "chef": {
                "server_url": "localhost",
                "validation_name": "bob",
                "json_attribs": None,
                "show_time": None,
            },
        }
        cc_chef.handle("chef", cfg, get_cloud(), [])
        c = util.load_text_file(cc_chef.CHEF_RB_PATH)
        assert "json_attribs" not in c
        assert "Formatter.show_time" not in c

    @skipIf(not CLIENT_TEMPL, "templates/chef_client.rb.tmpl is not available")
    def test_validation_cert_and_validation_key(self):
        # test validation_cert content is written to validation_key path
        util.write_file(
            "/etc/cloud/templates/chef_client.rb.tmpl", CLIENT_TEMPL
        )
        v_path = "/etc/chef/vkey.pem"
        v_cert = "this is my cert"
        cfg = {
            "chef": {
                "server_url": "localhost",
                "validation_name": "bob",
                "validation_key": v_path,
                "validation_cert": v_cert,
            },
        }
        cc_chef.handle("chef", cfg, get_cloud(), [])
        content = util.load_text_file(cc_chef.CHEF_RB_PATH)
        assert v_path in content
        util.load_text_file(v_path)
        assert v_cert == util.load_text_file(v_path)

    @skipIf(not CLIENT_TEMPL, "templates/chef_client.rb.tmpl is not available")
    def test_validation_cert_with_system(self):
        # test validation_cert content is not written over system file

        v_path = "/etc/chef/vkey.pem"
        v_cert = "system"
        expected_cert = "this is the system file certificate"
        cfg = {
            "chef": {
                "server_url": "localhost",
                "validation_name": "bob",
                "validation_key": v_path,
                "validation_cert": v_cert,
            },
        }
        util.write_file(
            "/etc/cloud/templates/chef_client.rb.tmpl", CLIENT_TEMPL
        )
        util.write_file(v_path, expected_cert)
        cc_chef.handle("chef", cfg, get_cloud(), [])
        content = util.load_text_file(cc_chef.CHEF_RB_PATH)
        assert v_path in content
        util.load_text_file(v_path)
        assert expected_cert == util.load_text_file(v_path)


@skipUnlessJsonSchema()
class TestBootCMDSchema:
    """Directly test schema rather than through handle."""

    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas tested by meta.examples in test_schema
            # Invalid schemas
            (
                {"chef": 1},
                "chef: 1 is not of type 'object'",
            ),
            (
                {"chef": {}},
                re.escape(" chef: {} ") + SCHEMA_EMPTY_ERROR,
            ),
            (
                {"chef": {"boguskey": True}},
                re.escape(
                    "chef: Additional properties are not allowed"
                    " ('boguskey' was unexpected)"
                ),
            ),
            (
                {"chef": {"directories": 1}},
                "chef.directories: 1 is not of type 'array'",
            ),
            (
                {"chef": {"directories": []}},
                re.escape("chef.directories: [] ") + SCHEMA_EMPTY_ERROR,
            ),
            (
                {"chef": {"directories": [1]}},
                "chef.directories.0: 1 is not of type 'string'",
            ),
            (
                {"chef": {"directories": ["a", "a"]}},
                re.escape(
                    "chef.directories: ['a', 'a'] has non-unique elements"
                ),
            ),
            (
                {"chef": {"validation_cert": 1}},
                "chef.validation_cert: 1 is not of type 'string'",
            ),
            (
                {"chef": {"validation_key": 1}},
                "chef.validation_key: 1 is not of type 'string'",
            ),
            (
                {"chef": {"firstboot_path": 1}},
                "chef.firstboot_path: 1 is not of type 'string'",
            ),
            (
                {"chef": {"client_key": 1}},
                "chef.client_key: 1 is not of type 'string'",
            ),
            (
                {"chef": {"encrypted_data_bag_secret": 1}},
                "chef.encrypted_data_bag_secret: 1 is not of type 'string'",
            ),
            (
                {"chef": {"environment": 1}},
                "chef.environment: 1 is not of type 'string'",
            ),
            (
                {"chef": {"file_backup_path": 1}},
                "chef.file_backup_path: 1 is not of type 'string'",
            ),
            (
                {"chef": {"file_cache_path": 1}},
                "chef.file_cache_path: 1 is not of type 'string'",
            ),
            (
                {"chef": {"json_attribs": 1}},
                "chef.json_attribs: 1 is not of type 'string'",
            ),
            (
                {"chef": {"log_level": 1}},
                "chef.log_level: 1 is not of type 'string'",
            ),
            (
                {"chef": {"log_location": 1}},
                "chef.log_location: 1 is not of type 'string'",
            ),
            (
                {"chef": {"node_name": 1}},
                "chef.node_name: 1 is not of type 'string'",
            ),
            (
                {"chef": {"omnibus_url": 1}},
                "chef.omnibus_url: 1 is not of type 'string'",
            ),
            (
                {"chef": {"omnibus_url_retries": "one"}},
                "chef.omnibus_url_retries: 'one' is not of type 'integer'",
            ),
            (
                {"chef": {"omnibus_version": 1}},
                "chef.omnibus_version: 1 is not of type 'string'",
            ),
            (
                {"chef": {"omnibus_version": 1}},
                "chef.omnibus_version: 1 is not of type 'string'",
            ),
            (
                {"chef": {"pid_file": 1}},
                "chef.pid_file: 1 is not of type 'string'",
            ),
            (
                {"chef": {"server_url": 1}},
                "chef.server_url: 1 is not of type 'string'",
            ),
            (
                {"chef": {"show_time": 1}},
                "chef.show_time: 1 is not of type 'boolean'",
            ),
            (
                {"chef": {"ssl_verify_mode": 1}},
                "chef.ssl_verify_mode: 1 is not of type 'string'",
            ),
            (
                {"chef": {"validation_name": 1}},
                "chef.validation_name: 1 is not of type 'string'",
            ),
            (
                {"chef": {"force_install": 1}},
                "chef.force_install: 1 is not of type 'boolean'",
            ),
            (
                {"chef": {"initial_attributes": 1}},
                "chef.initial_attributes: 1 is not of type 'object'",
            ),
            (
                {"chef": {"install_type": 1}},
                "chef.install_type: 1 is not of type 'string'",
            ),
            (
                {"chef": {"install_type": "bogusenum"}},
                re.escape(
                    "chef.install_type: 'bogusenum' is not one of"
                    " ['packages', 'gems', 'omnibus']"
                ),
            ),
            (
                {"chef": {"run_list": 1}},
                "chef.run_list: 1 is not of type 'array'",
            ),
            (
                {"chef": {"chef_license": 1}},
                "chef.chef_license: 1 is not of type 'string'",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Assert expected schema validation and error messages."""
        # New-style schema $defs exist in config/cloud-init-schema*.json
        schema = get_schema()
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, schema, strict=True)


class TestHelpers:
    def test_subp_blob_in_tempfile(self, mocker, tmpdir):
        mocker.patch(
            "tests.unittests.util.MockDistro.get_tmp_exec_path",
            return_value=tmpdir,
        )
        mocker.patch("cloudinit.temp_utils.mkdtemp", return_value=tmpdir)
        write_file = mocker.patch("cloudinit.util.write_file")
        m_subp = mocker.patch("cloudinit.config.cc_chef.subp.subp")
        distro = MockDistro()

        cc_chef.subp_blob_in_tempfile("hi", distro, args=[])
        assert m_subp.call_args == mock.call(args=[f"{tmpdir}/subp_blob"])
        assert write_file.call_args[0][1] == "hi"

    def test_subp_blob_in_tempfile_args(self, mocker, tmpdir):
        mocker.patch(
            "tests.unittests.util.MockDistro.get_tmp_exec_path",
            return_value=tmpdir,
        )
        mocker.patch("cloudinit.temp_utils.mkdtemp", return_value=tmpdir)
        write_file = mocker.patch("cloudinit.util.write_file")
        m_subp = mocker.patch("cloudinit.config.cc_chef.subp.subp")
        distro = MockDistro()

        cc_chef.subp_blob_in_tempfile("hi", distro, args=["aaa"])
        assert m_subp.call_args == mock.call(
            args=[f"{tmpdir}/subp_blob", "aaa"]
        )
        assert write_file.call_args[0][1] == "hi"
