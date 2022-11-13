# This file is part of cloud-init. See LICENSE file for license information.
import pytest

from cloudinit import subp
from cloudinit.config import cc_kernel_modules
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import CiTestCase, mock, skipUnlessJsonSchema

NL = "\n"
# Module path used in mocks
MPATH = "cloudinit.config.cc_kernel_modules"


class FakeCloud:
    def __init__(self, distro):
        self.distro = distro


class TestKernelModules(CiTestCase):

    with_logs = True
    allowed_subp = [CiTestCase.SUBP_SHELL_TRUE]

    def setUp(self):
        super(TestKernelModules, self).setUp()
        self.tmp = self.tmp_dir()

    def test_suppl_schema_error_on_missing_keys(self):
        """ValueError raised reporting any missing required keys"""
        cfg = {}
        match = (
            f"Invalid kernel_modules configuration:{NL}"
            "Missing required kernel_modules keys: name"
        )
        with self.assertRaisesRegex(ValueError, match):
            cc_kernel_modules.supplemental_schema_validation(cfg)

    def test_suppl_schema_error(self):
        """ValueError raised for any wrong values"""
        cfg = {
            "name": 1,
            "load": "no-bool",
            "persist": {
                "alias": 123,
                "install": 123,
                "blacklist": "no-bool",
                "softdep": {"pre": "not-an-array"},
            },
        }
        errors = [
            "Expected a string for kernel_modules:name. Found 1.",
            "Expected a boolean for kernel_modules:load. Found no-bool.",
            "Expected a string for kernel_modules:persist:alias. Found 123.",
            "Expected a string for kernel_modules:persist:install. Found 123.",
            "Expected a boolean for kernel_modules:persist:blacklist. "
            "Found no-bool.",
            "Expected an array for kernel_modules:persist:softdep:pre. "
            "Found not-an-array.",
        ]
        with self.assertRaises(ValueError) as context_mgr:
            cc_kernel_modules.supplemental_schema_validation(cfg)
        error_msg = str(context_mgr.exception)
        for error in errors:
            self.assertIn(error, error_msg)

    def test_prepare_module_failed(self):
        """Errors when trying to prepare modules"""
        module_name = "wireguard"

        CFG_FILES = cc_kernel_modules.DEFAULT_CONFIG["km_files"]
        with self.assertRaises(RuntimeError) as context_mgr:
            cc_kernel_modules.prepare_module(module_name)
        self.assertIn(
            "Failure appending kernel module 'wireguard' to file "
            f"{CFG_FILES['load']['path']}:\n",
            str(context_mgr.exception),
        )

    def test_enhance_module_failed(self):
        """Errors when trying to enhance modules"""
        module_name = "wireguard"
        persist = {
            "alias": "wireguard-alias",
            "install": "/usr/sbin/modprobe zfs",
        }
        unload_modules = []

        with self.assertRaises(RuntimeError) as context_mgr:
            cc_kernel_modules.enhance_module(
                module_name, persist, unload_modules
            )
        self.assertIn(
            "Failure enhancing kernel module 'wireguard':\n",
            str(context_mgr.exception),
        )

    def test_reload_modules_failed(self):
        """Errors when reloading modules"""
        distro = mock.MagicMock()  # No errors raised
        distro.manage_service.side_effect = subp.ProcessExecutionError(
            "Failed to find module 'ip_tables'"
        )
        mycloud = FakeCloud(distro)
        with self.assertRaises(RuntimeError) as context_mgr:
            cc_kernel_modules.reload_modules(mycloud)
        self.assertEqual(
            "Could not load modules with systemd-modules-load:\n"
            "Unexpected error while running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: Failed to find module 'ip_tables'\n"
            "Stderr: -",
            str(context_mgr.exception),
        )

    @mock.patch("%s.subp.subp" % MPATH)
    def test_update_initial_ramdisk_failed(self, m_subp):
        """Errors when updating initial ramdisk"""

        m_subp.side_effect = subp.ProcessExecutionError(
            "update-initramfs: execution error"
        )

        with self.assertRaises(RuntimeError) as context_mgr:
            cc_kernel_modules.update_initial_ramdisk()
        self.assertIn(
            "Failed to update initial ramdisk:\n"
            "Unexpected error while running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: update-initramfs: execution error\nStderr: -",
            str(context_mgr.exception),
        )

    @mock.patch("cloudinit.util.del_file")
    def test_cleanup_failed(self, m_wr):
        """Errors when tydying system up"""

        m_wr.side_effect = Exception("file write exception")

        CFG_FILES = cc_kernel_modules.DEFAULT_CONFIG["km_files"]
        with self.assertRaises(RuntimeError) as context_mgr:
            cc_kernel_modules.cleanup()
        self.assertIn(
            f"Could not delete file {CFG_FILES['load']['path']}:\n",
            str(context_mgr.exception),
        )

    @mock.patch("%s.subp.subp" % MPATH)
    @mock.patch("%s.is_loaded" % MPATH)
    def test_unload_failed(self, m_subp, m_is_loaded):
        """Errors when unloading kernel modules"""

        m_subp.side_effect = subp.ProcessExecutionError("unload exception")
        m_is_loaded.return_value = True

        unload_modules = ["wireguard"]

        with self.assertRaises(RuntimeError) as context_mgr:
            cc_kernel_modules.unload(unload_modules)
        self.assertIn(
            "Could not unload kernel module wireguard:\n",
            str(context_mgr.exception),
        )


class TestKernelModulesSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Valid schemas
            (
                {
                    "kernel_modules": [
                        {
                            "name": "wireguard",
                            "load": True,
                        }
                    ]
                },
                None,
            ),
            (
                {
                    "kernel_modules": [
                        {
                            "name": "v4l2loopback",
                            "load": True,
                            "persist": {
                                "options": "devices=1 video_nr=20 "
                                "card_label=fakecam exclusive_caps=1"
                            },
                        }
                    ]
                },
                None,
            ),
            (
                {
                    "kernel_modules": [
                        {"name": "zfs", "persist": {"blacklist": True}}
                    ]
                },
                None,
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is not None:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
