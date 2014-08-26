import os
import stat
import yaml

from mocker import MockerTestCase
from . import helpers
import unittest

from cloudinit import importer
from cloudinit import util


class FakeSelinux(object):

    def __init__(self, match_what):
        self.match_what = match_what
        self.restored = []

    def matchpathcon(self, path, mode):
        if path == self.match_what:
            return
        else:
            raise OSError("No match!")

    def is_selinux_enabled(self):
        return True

    def restorecon(self, path, recursive):
        self.restored.append(path)


class TestGetCfgOptionListOrStr(unittest.TestCase):
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
        my_file = os.path.join(self.tmp, "my_file")
        with open(my_file, "w") as fp:
            fp.write("My Content")

        import_mock = self.mocker.replace(importer.import_module,
                                          passthrough=False)
        import_mock('selinux')

        fake_se = FakeSelinux(my_file)
        self.mocker.result(fake_se)
        self.mocker.replay()
        with util.SeLinuxGuard(my_file) as is_on:
            self.assertTrue(is_on)
        self.assertEqual(1, len(fake_se.restored))
        self.assertEqual(my_file, fake_se.restored[0])


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


class TestKeyValStrings(unittest.TestCase):
    def test_keyval_str_to_dict(self):
        expected = {'1': 'one', '2': 'one+one', 'ro': True}
        cmdline = "1=one ro 2=one+one"
        self.assertEqual(expected, util.keyval_str_to_dict(cmdline))


class TestGetCmdline(unittest.TestCase):
    def test_cmdline_reads_debug_env(self):
        os.environ['DEBUG_PROC_CMDLINE'] = 'abcd 123'
        self.assertEqual(os.environ['DEBUG_PROC_CMDLINE'], util.get_cmdline())


class TestLoadYaml(unittest.TestCase):
    mydefault = "7b03a8ebace993d806255121073fed52"

    def test_simple(self):
        mydata = {'1': "one", '2': "two"}
        self.assertEqual(util.load_yaml(yaml.dump(mydata)), mydata)

    def test_nonallowed_returns_default(self):
        # for now, anything not in the allowed list just returns the default.
        myyaml = yaml.dump({'1': "one"})
        self.assertEqual(util.load_yaml(blob=myyaml,
                                        default=self.mydefault,
                                        allowed=(str,)),
                         self.mydefault)

    def test_bogus_returns_default(self):
        badyaml = "1\n 2:"
        self.assertEqual(util.load_yaml(blob=badyaml,
                                        default=self.mydefault),
                         self.mydefault)

    def test_unsafe_types(self):
        # should not load complex types
        unsafe_yaml = yaml.dump((1, 2, 3,))
        self.assertEqual(util.load_yaml(blob=unsafe_yaml,
                                        default=self.mydefault),
                         self.mydefault)

    def test_python_unicode(self):
        # complex type of python/unicde is explicitly allowed
        myobj = {'1': unicode("FOOBAR")}
        safe_yaml = yaml.dump(myobj)
        self.assertEqual(util.load_yaml(blob=safe_yaml,
                                        default=self.mydefault),
                         myobj)


class TestMountinfoParsing(helpers.ResourceUsingTestCase):
    def test_invalid_mountinfo(self):
        line = ("20 1 252:1 / / rw,relatime - ext4 /dev/mapper/vg0-root"
                "rw,errors=remount-ro,data=ordered")
        elements = line.split()
        for i in range(len(elements) + 1):
            lines = [' '.join(elements[0:i])]
            if i < 10:
                expected = None
            else:
                expected = ('/dev/mapper/vg0-root', 'ext4', '/')
            self.assertEqual(expected, util.parse_mount_info('/', lines))

    def test_precise_ext4_root(self):

        lines = self.readResource('mountinfo_precise_ext4.txt').splitlines()

        expected = ('/dev/mapper/vg0-root', 'ext4', '/')
        self.assertEqual(expected, util.parse_mount_info('/', lines))
        self.assertEqual(expected, util.parse_mount_info('/usr', lines))
        self.assertEqual(expected, util.parse_mount_info('/usr/bin', lines))

        expected = ('/dev/md0', 'ext4', '/boot')
        self.assertEqual(expected, util.parse_mount_info('/boot', lines))
        self.assertEqual(expected, util.parse_mount_info('/boot/grub', lines))

        expected = ('/dev/mapper/vg0-root', 'ext4', '/')
        self.assertEqual(expected, util.parse_mount_info('/home', lines))
        self.assertEqual(expected, util.parse_mount_info('/home/me', lines))

        expected = ('tmpfs', 'tmpfs', '/run')
        self.assertEqual(expected, util.parse_mount_info('/run', lines))

        expected = ('none', 'tmpfs', '/run/lock')
        self.assertEqual(expected, util.parse_mount_info('/run/lock', lines))

    def test_raring_btrfs_root(self):
        lines = self.readResource('mountinfo_raring_btrfs.txt').splitlines()

        expected = ('/dev/vda1', 'btrfs', '/')
        self.assertEqual(expected, util.parse_mount_info('/', lines))
        self.assertEqual(expected, util.parse_mount_info('/usr', lines))
        self.assertEqual(expected, util.parse_mount_info('/usr/bin', lines))
        self.assertEqual(expected, util.parse_mount_info('/boot', lines))
        self.assertEqual(expected, util.parse_mount_info('/boot/grub', lines))

        expected = ('/dev/vda1', 'btrfs', '/home')
        self.assertEqual(expected, util.parse_mount_info('/home', lines))
        self.assertEqual(expected, util.parse_mount_info('/home/me', lines))

        expected = ('tmpfs', 'tmpfs', '/run')
        self.assertEqual(expected, util.parse_mount_info('/run', lines))

        expected = ('none', 'tmpfs', '/run/lock')
        self.assertEqual(expected, util.parse_mount_info('/run/lock', lines))

# vi: ts=4 expandtab
