import os
import shutil
import tempfile
from unittest import mock

from cloudinit import dmi, subp, util
from tests.unittests import helpers


class TestReadDMIData(helpers.FilesystemMockingTestCase):
    def setUp(self):
        super(TestReadDMIData, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)
        self.reRoot(self.new_root)
        p = mock.patch("cloudinit.dmi.is_container", return_value=False)
        self.addCleanup(p.stop)
        self._m_is_container = p.start()
        p = mock.patch("cloudinit.dmi.is_FreeBSD", return_value=False)
        self.addCleanup(p.stop)
        self._m_is_FreeBSD = p.start()

    def _create_sysfs_parent_directory(self):
        util.ensure_dir(os.path.join("sys", "class", "dmi", "id"))

    def _create_sysfs_file(self, key, content):
        """Mocks the sys path found on Linux systems."""
        self._create_sysfs_parent_directory()
        dmi_key = "/sys/class/dmi/id/{0}".format(key)
        util.write_file(dmi_key, content)

    def _configure_dmidecode_return(self, key, content, error=None):
        """
        In order to test a missing sys path and call outs to dmidecode, this
        function fakes the results of dmidecode to test the results.
        """

        def _dmidecode_subp(cmd):
            if cmd[-1] != key:
                raise subp.ProcessExecutionError()
            return (content, error)

        self.patched_funcs.enter_context(
            mock.patch("cloudinit.dmi.subp.which", side_effect=lambda _: True)
        )
        self.patched_funcs.enter_context(
            mock.patch("cloudinit.dmi.subp.subp", side_effect=_dmidecode_subp)
        )

    def _configure_kenv_return(self, key, content, error=None):
        """
        In order to test a FreeBSD system call outs to kenv, this
        function fakes the results of kenv to test the results.
        """

        def _kenv_subp(cmd):
            if cmd[-1] != dmi.DMIDECODE_TO_KERNEL[key].freebsd:
                raise subp.ProcessExecutionError()
            return (content, error)

        self.patched_funcs.enter_context(
            mock.patch("cloudinit.dmi.subp.subp", side_effect=_kenv_subp)
        )

    def patch_mapping(self, new_mapping):
        self.patched_funcs.enter_context(
            mock.patch("cloudinit.dmi.DMIDECODE_TO_KERNEL", new_mapping)
        )

    def test_sysfs_used_with_key_in_mapping_and_file_on_disk(self):
        self.patch_mapping({"mapped-key": dmi.kdmi("mapped-value", None)})
        expected_dmi_value = "sys-used-correctly"
        self._create_sysfs_file("mapped-value", expected_dmi_value)
        self._configure_dmidecode_return("mapped-key", "wrong-wrong-wrong")
        self.assertEqual(expected_dmi_value, dmi.read_dmi_data("mapped-key"))

    def test_dmidecode_used_if_no_sysfs_file_on_disk(self):
        self.patch_mapping({})
        self._create_sysfs_parent_directory()
        expected_dmi_value = "dmidecode-used"
        self._configure_dmidecode_return("use-dmidecode", expected_dmi_value)
        with mock.patch("cloudinit.util.os.uname") as m_uname:
            m_uname.return_value = (
                "x-sysname",
                "x-nodename",
                "x-release",
                "x-version",
                "x86_64",
            )
            self.assertEqual(
                expected_dmi_value, dmi.read_dmi_data("use-dmidecode")
            )

    def test_dmidecode_not_used_on_arm(self):
        self.patch_mapping({})
        print("current =%s", subp)
        self._create_sysfs_parent_directory()
        dmi_val = "from-dmidecode"
        dmi_name = "use-dmidecode"
        self._configure_dmidecode_return(dmi_name, dmi_val)
        print("now =%s", subp)

        expected = {"armel": None, "aarch64": dmi_val, "x86_64": dmi_val}
        found = {}
        # we do not run the 'dmi-decode' binary on some arches
        # verify that anything requested that is not in the sysfs dir
        # will return None on those arches.
        with mock.patch("cloudinit.util.os.uname") as m_uname:
            for arch in expected:
                m_uname.return_value = (
                    "x-sysname",
                    "x-nodename",
                    "x-release",
                    "x-version",
                    arch,
                )
                print("now2 =%s", subp)
                found[arch] = dmi.read_dmi_data(dmi_name)
        self.assertEqual(expected, found)

    def test_none_returned_if_neither_source_has_data(self):
        self.patch_mapping({})
        self._configure_dmidecode_return("key", "value")
        self.assertIsNone(dmi.read_dmi_data("expect-fail"))

    def test_none_returned_if_dmidecode_not_in_path(self):
        self.patched_funcs.enter_context(
            mock.patch.object(subp, "which", lambda _: False)
        )
        self.patch_mapping({})
        self.assertIsNone(dmi.read_dmi_data("expect-fail"))

    def test_empty_string_returned_instead_of_foxfox(self):
        # uninitialized dmi values show as \xff, return empty string
        my_len = 32
        dmi_value = b"\xff" * my_len + b"\n"
        expected = ""
        dmi_key = "system-product-name"
        sysfs_key = "product_name"
        self._create_sysfs_file(sysfs_key, dmi_value)
        self.assertEqual(expected, dmi.read_dmi_data(dmi_key))

    def test_container_returns_none(self):
        """In a container read_dmi_data should always return None."""

        # first verify we get the value if not in container
        self._m_is_container.return_value = False
        key, val = ("system-product-name", "my_product")
        self._create_sysfs_file("product_name", val)
        self.assertEqual(val, dmi.read_dmi_data(key))

        # then verify in container returns None
        self._m_is_container.return_value = True
        self.assertIsNone(dmi.read_dmi_data(key))

    def test_container_returns_none_on_unknown(self):
        """In a container even bogus keys return None."""
        self._m_is_container.return_value = True
        self._create_sysfs_file("product_name", "should-be-ignored")
        self.assertIsNone(dmi.read_dmi_data("bogus"))
        self.assertIsNone(dmi.read_dmi_data("system-product-name"))

    def test_freebsd_uses_kenv(self):
        """On a FreeBSD system, kenv is called."""
        self._m_is_FreeBSD.return_value = True
        key, val = ("system-product-name", "my_product")
        self._configure_kenv_return(key, val)
        self.assertEqual(dmi.read_dmi_data(key), val)
