# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.cc_runcmd import handle, schema
from cloudinit.sources import DataSourceNone
from cloudinit import (distros, helpers, cloud, util)
from cloudinit.tests.helpers import (
    CiTestCase, FilesystemMockingTestCase, SchemaTestCaseMixin,
    skipUnlessJsonSchema)

import logging
import os
import stat

LOG = logging.getLogger(__name__)


class TestRuncmd(FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestRuncmd, self).setUp()
        self.subp = util.subp
        self.new_root = self.tmp_dir()

    def _get_cloud(self, distro):
        self.patchUtils(self.new_root)
        paths = helpers.Paths({'scripts': self.new_root})
        cls = distros.fetch(distro)
        mydist = cls(distro, {}, paths)
        myds = DataSourceNone.DataSourceNone({}, mydist, paths)
        paths.datasource = myds
        return cloud.Cloud(myds, paths, {}, mydist, None)

    def test_handler_skip_if_no_runcmd(self):
        """When the provided config doesn't contain runcmd, skip it."""
        cfg = {}
        mycloud = self._get_cloud('ubuntu')
        handle('notimportant', cfg, mycloud, LOG, None)
        self.assertIn(
            "Skipping module named notimportant, no 'runcmd' key",
            self.logs.getvalue())

    def test_handler_invalid_command_set(self):
        """Commands which can't be converted to shell will raise errors."""
        invalid_config = {'runcmd': 1}
        cc = self._get_cloud('ubuntu')
        handle('cc_runcmd', invalid_config, cc, LOG, [])
        self.assertIn(
            'Failed to shellify 1 into file'
            ' /var/lib/cloud/instances/iid-datasource-none/scripts/runcmd',
            self.logs.getvalue())

    @skipUnlessJsonSchema()
    def test_handler_schema_validation_warns_non_array_type(self):
        """Schema validation warns of non-array type for runcmd key.

        Schema validation is not strict, so runcmd attempts to shellify the
        invalid content.
        """
        invalid_config = {'runcmd': 1}
        cc = self._get_cloud('ubuntu')
        handle('cc_runcmd', invalid_config, cc, LOG, [])
        self.assertIn(
            'Invalid config:\nruncmd: 1 is not of type \'array\'',
            self.logs.getvalue())
        self.assertIn('Failed to shellify', self.logs.getvalue())

    @skipUnlessJsonSchema()
    def test_handler_schema_validation_warns_non_array_item_type(self):
        """Schema validation warns of non-array or string runcmd items.

        Schema validation is not strict, so runcmd attempts to shellify the
        invalid content.
        """
        invalid_config = {
            'runcmd': ['ls /', 20, ['wget', 'http://stuff/blah'], {'a': 'n'}]}
        cc = self._get_cloud('ubuntu')
        handle('cc_runcmd', invalid_config, cc, LOG, [])
        expected_warnings = [
            'runcmd.1: 20 is not valid under any of the given schemas',
            'runcmd.3: {\'a\': \'n\'} is not valid under any of the given'
            ' schema'
        ]
        logs = self.logs.getvalue()
        for warning in expected_warnings:
            self.assertIn(warning, logs)
        self.assertIn('Failed to shellify', logs)

    def test_handler_write_valid_runcmd_schema_to_file(self):
        """Valid runcmd schema is written to a runcmd shell script."""
        valid_config = {'runcmd': [['ls', '/']]}
        cc = self._get_cloud('ubuntu')
        handle('cc_runcmd', valid_config, cc, LOG, [])
        runcmd_file = os.path.join(
            self.new_root,
            'var/lib/cloud/instances/iid-datasource-none/scripts/runcmd')
        self.assertEqual("#!/bin/sh\n'ls' '/'\n", util.load_file(runcmd_file))
        file_stat = os.stat(runcmd_file)
        self.assertEqual(0o700, stat.S_IMODE(file_stat.st_mode))


@skipUnlessJsonSchema()
class TestSchema(CiTestCase, SchemaTestCaseMixin):
    """Directly test schema rather than through handle."""

    schema = schema

    def test_duplicates_are_fine_array_array(self):
        """Duplicated commands array/array entries are allowed."""
        self.assertSchemaValid(
            [["echo", "bye"], ["echo", "bye"]],
            "command entries can be duplicate.")

    def test_duplicates_are_fine_array_string(self):
        """Duplicated commands array/string entries are allowed."""
        self.assertSchemaValid(
            ["echo bye", "echo bye"],
            "command entries can be duplicate.")

# vi: ts=4 expandtab
