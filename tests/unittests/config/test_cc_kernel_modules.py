# This file is part of cloud-init. See LICENSE file for license information.
from unittest import mock

import pytest

from cloudinit import subp
from cloudinit.config import cc_kernel_modules
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

NL = "\n"
# Module path used in mocks
MPATH = "cloudinit.config.cc_kernel_modules"


class TestKernelModules:
    def test_suppl_schema_error_on_missing_keys(self):
        """ValueError raised reporting any missing required keys"""
        cfg = {}
        match = (
            f"Invalid kernel_modules configuration:{NL}"
            "Missing required kernel_modules keys: name"
        )
        with pytest.raises(ValueError, match=match):
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
        with pytest.raises(ValueError) as context_mgr:
            cc_kernel_modules.supplemental_schema_validation(cfg)
        error_msg = str(context_mgr.value)
        for error in errors:
            assert error in error_msg

    def test_prepare_module_failed(self):
        """Errors when trying to prepare modules"""
        module_name = "wireguard"

        CFG_FILES = cc_kernel_modules.DEFAULT_CONFIG
        with pytest.raises(RuntimeError) as context_mgr:
            cc_kernel_modules.prepare_module(module_name)
        assert (
            "Failure appending kernel module 'wireguard' to file "
            f"{CFG_FILES['load']['path']}:\n"
        ) in str(context_mgr.value)

    def test_enhance_module_failed(self):
        """Errors when trying to enhance modules"""
        module_name = "wireguard"
        persist = {
            "alias": "wireguard-alias",
            "install": "/usr/sbin/modprobe zfs",
        }
        match = "Failure enhancing kernel module 'wireguard':\n"
        with pytest.raises(RuntimeError, match=match):
            cc_kernel_modules.enhance_module(
                module_name=module_name, persist=persist, unload_modules=[]
            )

    def test_reload_modules_failed(self):
        """Errors when reloading modules"""
        # distro = mock.MagicMock()  # No errors raised
        # distro.manage_service.side_effect = subp.ProcessExecutionError(
        #   "Failed to find module 'ip_tables'"
        # )
        mycloud = get_cloud()
        match = (
            "Could not load modules with systemd-modules-load:\n"
            "Unexpected error while running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: Failed to find module 'ip_tables'\n"
            "Stderr: -"
        )
        with mock.patch.object(mycloud.distro, "manage_service") as manage_svc:
            manage_svc.side_effect = subp.ProcessExecutionError(
                "Failed to find module 'ip_tables'"
            )

            with pytest.raises(RuntimeError, match=match):
                cc_kernel_modules.reload_modules(mycloud)

    @mock.patch("%s.subp.subp" % MPATH)
    def test_update_initial_ramdisk_failed(self, m_subp):
        """Errors when updating initial ramdisk"""

        m_subp.side_effect = subp.ProcessExecutionError(
            "update-initramfs: execution error"
        )

        match = (
            "Failed to update initial ramdisk:\n"
            "Unexpected error while running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: update-initramfs: execution error\nStderr: -"
        )
        mycloud = get_cloud()
        with pytest.raises(RuntimeError, match=match):
            cc_kernel_modules.update_initial_ramdisk(mycloud)

    @mock.patch("cloudinit.util.del_file")
    def test_cleanup_failed(self, m_wr):
        """Errors when tydying system up"""

        m_wr.side_effect = Exception("file write exception")

        CFG_FILES = cc_kernel_modules.DEFAULT_CONFIG
        error_msg = f"Could not delete file {CFG_FILES['load']['path']}:\n"
        with pytest.raises(RuntimeError, match=error_msg):
            cc_kernel_modules.cleanup()

    def test_wb_unload_failed(self):
        """Errors when unloading kernel modules"""

        mycloud = get_cloud()

        def fake_manage_kernel_module(action, module=""):
            if action == "list":
                return ("kvm\nwireguard", "")
            else:
                raise subp.ProcessExecutionError("unload exception")

        match = "Could not unload kernel module wireguard:\n"
        with mock.patch.object(
            mycloud.distro,
            "manage_kernel_module",
            side_effect=fake_manage_kernel_module,
        ):
            with pytest.raises(RuntimeError, match=match):
                cc_kernel_modules.unload(cloud=mycloud, modules=["wireguard"])


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
