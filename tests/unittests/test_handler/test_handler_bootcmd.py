# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.cc_bootcmd import handle, schema
from cloudinit.sources import DataSourceNone
from cloudinit import (distros, helpers, cloud, util)
from cloudinit.tests.helpers import (
    CiTestCase, mock, SchemaTestCaseMixin, skipUnlessJsonSchema)

import logging
import tempfile


LOG = logging.getLogger(__name__)


class FakeExtendedTempFile(object):
    def __init__(self, suffix):
        self.suffix = suffix
        self.handle = tempfile.NamedTemporaryFile(
            prefix="ci-%s." % self.__class__.__name__, delete=False)

    def __enter__(self):
        return self.handle

    def __exit__(self, exc_type, exc_value, traceback):
        self.handle.close()
        util.del_file(self.handle.name)


class TestBootcmd(CiTestCase):

    with_logs = True

    _etmpfile_path = ('cloudinit.config.cc_bootcmd.temp_utils.'
                      'ExtendedTemporaryFile')

    def setUp(self):
        super(TestBootcmd, self).setUp()
        self.subp = util.subp
        self.new_root = self.tmp_dir()

    def _get_cloud(self, distro):
        paths = helpers.Paths({})
        cls = distros.fetch(distro)
        mydist = cls(distro, {}, paths)
        myds = DataSourceNone.DataSourceNone({}, mydist, paths)
        paths.datasource = myds
        return cloud.Cloud(myds, paths, {}, mydist, None)

    def test_handler_skip_if_no_bootcmd(self):
        """When the provided config doesn't contain bootcmd, skip it."""
        cfg = {}
        mycloud = self._get_cloud('ubuntu')
        handle('notimportant', cfg, mycloud, LOG, None)
        self.assertIn(
            "Skipping module named notimportant, no 'bootcmd' key",
            self.logs.getvalue())

    def test_handler_invalid_command_set(self):
        """Commands which can't be converted to shell will raise errors."""
        invalid_config = {'bootcmd': 1}
        cc = self._get_cloud('ubuntu')
        with self.assertRaises(TypeError) as context_manager:
            handle('cc_bootcmd', invalid_config, cc, LOG, [])
        self.assertIn('Failed to shellify bootcmd', self.logs.getvalue())
        self.assertEqual(
            "Input to shellify was type 'int'. Expected list or tuple.",
            str(context_manager.exception))

    @skipUnlessJsonSchema()
    def test_handler_schema_validation_warns_non_array_type(self):
        """Schema validation warns of non-array type for bootcmd key.

        Schema validation is not strict, so bootcmd attempts to shellify the
        invalid content.
        """
        invalid_config = {'bootcmd': 1}
        cc = self._get_cloud('ubuntu')
        with self.assertRaises(TypeError):
            handle('cc_bootcmd', invalid_config, cc, LOG, [])
        self.assertIn(
            'Invalid config:\nbootcmd: 1 is not of type \'array\'',
            self.logs.getvalue())
        self.assertIn('Failed to shellify', self.logs.getvalue())

    @skipUnlessJsonSchema()
    def test_handler_schema_validation_warns_non_array_item_type(self):
        """Schema validation warns of non-array or string bootcmd items.

        Schema validation is not strict, so bootcmd attempts to shellify the
        invalid content.
        """
        invalid_config = {
            'bootcmd': ['ls /', 20, ['wget', 'http://stuff/blah'], {'a': 'n'}]}
        cc = self._get_cloud('ubuntu')
        with self.assertRaises(TypeError) as context_manager:
            handle('cc_bootcmd', invalid_config, cc, LOG, [])
        expected_warnings = [
            'bootcmd.1: 20 is not valid under any of the given schemas',
            'bootcmd.3: {\'a\': \'n\'} is not valid under any of the given'
            ' schema'
        ]
        logs = self.logs.getvalue()
        for warning in expected_warnings:
            self.assertIn(warning, logs)
        self.assertIn('Failed to shellify', logs)
        self.assertEqual(
            ("Unable to shellify type 'int'. Expected list, string, tuple. "
             "Got: 20"),
            str(context_manager.exception))

    def test_handler_creates_and_runs_bootcmd_script_with_instance_id(self):
        """Valid schema runs a bootcmd script with INSTANCE_ID in the env."""
        cc = self._get_cloud('ubuntu')
        out_file = self.tmp_path('bootcmd.out', self.new_root)
        my_id = "b6ea0f59-e27d-49c6-9f87-79f19765a425"
        valid_config = {'bootcmd': [
            'echo {0} $INSTANCE_ID > {1}'.format(my_id, out_file)]}

        with mock.patch(self._etmpfile_path, FakeExtendedTempFile):
            handle('cc_bootcmd', valid_config, cc, LOG, [])
        self.assertEqual(my_id + ' iid-datasource-none\n',
                         util.load_file(out_file))

    def test_handler_runs_bootcmd_script_with_error(self):
        """When a valid script generates an error, that error is raised."""
        cc = self._get_cloud('ubuntu')
        valid_config = {'bootcmd': ['exit 1']}  # Script with error

        with mock.patch(self._etmpfile_path, FakeExtendedTempFile):
            with self.assertRaises(util.ProcessExecutionError) as ctxt_manager:
                handle('does-not-matter', valid_config, cc, LOG, [])
        self.assertIn(
            'Unexpected error while running command.\n'
            "Command: ['/bin/sh',",
            str(ctxt_manager.exception))
        self.assertIn(
            'Failed to run bootcmd module does-not-matter',
            self.logs.getvalue())


@skipUnlessJsonSchema()
class TestSchema(CiTestCase, SchemaTestCaseMixin):
    """Directly test schema rather than through handle."""

    schema = schema

    def test_duplicates_are_fine_array_array(self):
        """Duplicated commands array/array entries are allowed."""
        self.assertSchemaValid(
            ["byebye", "byebye"], 'command entries can be duplicate')

    def test_duplicates_are_fine_array_string(self):
        """Duplicated commands array/string entries are allowed."""
        self.assertSchemaValid(
            ["echo bye", "echo bye"], "command entries can be duplicate.")


# vi: ts=4 expandtab
