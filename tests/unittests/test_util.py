import os
import stat

from unittest import TestCase
from mocker import MockerTestCase

from cloudinit import util
from cloudinit import importer


class FakeSelinux(object):

    def __init__(self, match_what):
        self.match_what = match_what
        self.restored = []

    def matchpathcon(self, path, mode):  # pylint: disable=W0613
        if path == self.match_what:
            return
        else:
            raise OSError("No match!")

    def is_selinux_enabled(self):
        return True

    def restorecon(self, path, recursive):  # pylint: disable=W0613
        self.restored.append(path)


class TestMergeDict(MockerTestCase):
    def test_simple_merge(self):
        """Test simple non-conflict merge."""
        source = {"key1": "value1"}
        candidate = {"key2": "value2"}
        result = util.mergedict(source, candidate)
        self.assertEqual({"key1": "value1", "key2": "value2"}, result)

    def test_nested_merge(self):
        """Test nested merge."""
        source = {"key1": {"key1.1": "value1.1"}}
        candidate = {"key1": {"key1.2": "value1.2"}}
        result = util.mergedict(source, candidate)
        self.assertEqual(
            {"key1": {"key1.1": "value1.1", "key1.2": "value1.2"}}, result)

    def test_merge_does_not_override(self):
        """Test that candidate doesn't override source."""
        source = {"key1": "value1", "key2": "value2"}
        candidate = {"key1": "value2", "key2": "NEW VALUE"}
        result = util.mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_empty_candidate(self):
        """Test empty candidate doesn't change source."""
        source = {"key": "value"}
        candidate = {}
        result = util.mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_empty_source(self):
        """Test empty source is replaced by candidate."""
        source = {}
        candidate = {"key": "value"}
        result = util.mergedict(source, candidate)
        self.assertEqual(candidate, result)

    def test_non_dict_candidate(self):
        """Test non-dict candidate is discarded."""
        source = {"key": "value"}
        candidate = "not a dict"
        result = util.mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_non_dict_source(self):
        """Test non-dict source is not modified with a dict candidate."""
        source = "not a dict"
        candidate = {"key": "value"}
        result = util.mergedict(source, candidate)
        self.assertEqual(source, result)

    def test_neither_dict(self):
        """Test if neither candidate or source is dict source wins."""
        source = "source"
        candidate = "candidate"
        result = util.mergedict(source, candidate)
        self.assertEqual(source, result)


class TestGetCfgOptionListOrStr(TestCase):
    def test_not_found_no_default(self):
        """None is returned if key is not found and no default given."""
        config = {}
        result = util.get_cfg_option_list(config, "key")
        self.assertEqual(None, result)

    def test_not_found_with_default(self):
        """Default is returned if key is not found."""
        config = {}
        result = util.get_cfg_option_list(config, "key", default=["DEFAULT"])
        self.assertEqual(["DEFAULT"], result)

    def test_found_with_default(self):
        """Default is not returned if key is found."""
        config = {"key": ["value1"]}
        result = util.get_cfg_option_list(config, "key", default=["DEFAULT"])
        self.assertEqual(["value1"], result)

    def test_found_convert_to_list(self):
        """Single string is converted to one element list."""
        config = {"key": "value1"}
        result = util.get_cfg_option_list(config, "key")
        self.assertEqual(["value1"], result)

    def test_value_is_none(self):
        """If value is None empty list is returned."""
        config = {"key": None}
        result = util.get_cfg_option_list(config, "key")
        self.assertEqual([], result)


class TestWriteFile(MockerTestCase):
    def setUp(self):
        super(TestWriteFile, self).setUp()
        self.tmp = self.makeDir(prefix="unittest_")

    def test_basic_usage(self):
        """Verify basic usage with default args."""
        path = os.path.join(self.tmp, "NewFile.txt")
        contents = "Hey there"

        util.write_file(path, contents)

        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.isfile(path))
        with open(path) as f:
            create_contents = f.read()
            self.assertEqual(contents, create_contents)
        file_stat = os.stat(path)
        self.assertEqual(0644, stat.S_IMODE(file_stat.st_mode))

    def test_dir_is_created_if_required(self):
        """Verifiy that directories are created is required."""
        dirname = os.path.join(self.tmp, "subdir")
        path = os.path.join(dirname, "NewFile.txt")
        contents = "Hey there"

        util.write_file(path, contents)

        self.assertTrue(os.path.isdir(dirname))
        self.assertTrue(os.path.isfile(path))

    def test_custom_mode(self):
        """Verify custom mode works properly."""
        path = os.path.join(self.tmp, "NewFile.txt")
        contents = "Hey there"

        util.write_file(path, contents, mode=0666)

        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.isfile(path))
        file_stat = os.stat(path)
        self.assertEqual(0666, stat.S_IMODE(file_stat.st_mode))

    def test_custom_omode(self):
        """Verify custom omode works properly."""
        path = os.path.join(self.tmp, "NewFile.txt")
        contents = "Hey there"

        # Create file first with basic content
        with open(path, "wb") as f:
            f.write("LINE1\n")
        util.write_file(path, contents, omode="a")

        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.isfile(path))
        with open(path) as f:
            create_contents = f.read()
            self.assertEqual("LINE1\nHey there", create_contents)

    def test_restorecon_if_possible_is_called(self):
        """Make sure the selinux guard is called correctly."""
        import_mock = self.mocker.replace(importer.import_module,
                                          passthrough=False)
        import_mock('selinux')
        fake_se = FakeSelinux('/etc/hosts')
        self.mocker.result(fake_se)
        self.mocker.replay()
        with util.SeLinuxGuard("/etc/hosts") as is_on:
            self.assertTrue(is_on)
        self.assertEqual(1, len(fake_se.restored))
        self.assertEqual('/etc/hosts', fake_se.restored[0])


class TestDeleteDirContents(MockerTestCase):
    def setUp(self):
        super(TestDeleteDirContents, self).setUp()
        self.tmp = self.makeDir(prefix="unittest_")

    def assertDirEmpty(self, dirname):
        self.assertEqual([], os.listdir(dirname))

    def test_does_not_delete_dir(self):
        """Ensure directory itself is not deleted."""
        util.delete_dir_contents(self.tmp)

        self.assertTrue(os.path.isdir(self.tmp))
        self.assertDirEmpty(self.tmp)

    def test_deletes_files(self):
        """Single file should be deleted."""
        with open(os.path.join(self.tmp, "new_file.txt"), "wb") as f:
            f.write("DELETE ME")

        util.delete_dir_contents(self.tmp)

        self.assertDirEmpty(self.tmp)

    def test_deletes_empty_dirs(self):
        """Empty directories should be deleted."""
        os.mkdir(os.path.join(self.tmp, "new_dir"))

        util.delete_dir_contents(self.tmp)

        self.assertDirEmpty(self.tmp)

    def test_deletes_nested_dirs(self):
        """Nested directories should be deleted."""
        os.mkdir(os.path.join(self.tmp, "new_dir"))
        os.mkdir(os.path.join(self.tmp, "new_dir", "new_subdir"))

        util.delete_dir_contents(self.tmp)

        self.assertDirEmpty(self.tmp)

    def test_deletes_non_empty_dirs(self):
        """Non-empty directories should be deleted."""
        os.mkdir(os.path.join(self.tmp, "new_dir"))
        f_name = os.path.join(self.tmp, "new_dir", "new_file.txt")
        with open(f_name, "wb") as f:
            f.write("DELETE ME")

        util.delete_dir_contents(self.tmp)

        self.assertDirEmpty(self.tmp)

    def test_deletes_symlinks(self):
        """Symlinks should be deleted."""
        file_name = os.path.join(self.tmp, "new_file.txt")
        link_name = os.path.join(self.tmp, "new_file_link.txt")
        with open(file_name, "wb") as f:
            f.write("DELETE ME")
        os.symlink(file_name, link_name)

        util.delete_dir_contents(self.tmp)

        self.assertDirEmpty(self.tmp)


class TestKeyValStrings(TestCase):
    def test_keyval_str_to_dict(self):
        expected = {'1': 'one', '2': 'one+one', 'ro': True}
        cmdline = "1=one ro 2=one+one"
        self.assertEqual(expected, util.keyval_str_to_dict(cmdline))


class TestGetCmdline(TestCase):
    def test_cmdline_reads_debug_env(self):
        os.environ['DEBUG_PROC_CMDLINE'] = 'abcd 123'
        self.assertEqual(os.environ['DEBUG_PROC_CMDLINE'], util.get_cmdline())

# vi: ts=4 expandtab
