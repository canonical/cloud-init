# This file is part of cloud-init. See LICENSE file for license information.
import re

import pytest

from cloudinit.config import cc_users_groups
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    CiTestCase,
    does_not_raise,
    mock,
    skipUnlessJsonSchema,
)

MODPATH = "cloudinit.config.cc_users_groups"


@mock.patch("cloudinit.distros.ubuntu.Distro.create_group")
@mock.patch("cloudinit.distros.ubuntu.Distro.create_user")
class TestHandleUsersGroups(CiTestCase):
    """Test cc_users_groups handling of config."""

    with_logs = True

    def test_handle_no_cfg_creates_no_users_or_groups(self, m_user, m_group):
        """Test handle with no config will not create users or groups."""
        cfg = {}  # merged cloud-config
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None)
        m_user.assert_not_called()
        m_group.assert_not_called()

    def test_handle_users_in_cfg_calls_create_users(self, m_user, m_group):
        """When users in config, create users with distro.create_user."""
        cfg = {"users": ["default", {"name": "me2"}]}  # merged cloud-config
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None)
        self.assertCountEqual(
            m_user.call_args_list,
            [
                mock.call(
                    "ubuntu",
                    groups="lxd,sudo",
                    lock_passwd=True,
                    shell="/bin/bash",
                ),
                mock.call("me2", default=False),
            ],
        )
        m_group.assert_not_called()

    @mock.patch("cloudinit.distros.freebsd.Distro.create_group")
    @mock.patch("cloudinit.distros.freebsd.Distro.create_user")
    def test_handle_users_in_cfg_calls_create_users_on_bsd(
        self,
        m_fbsd_user,
        m_fbsd_group,
        m_linux_user,
        m_linux_group,
    ):
        """When users in config, create users with freebsd.create_user."""
        cfg = {
            "users": ["default", {"name": "me2", "uid": 1234}]
        }  # merged cloud-config
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "freebsd",
                "lock_passwd": True,
                "groups": ["wheel"],
                "shell": "/bin/tcsh",
                "homedir": "/home/freebsd",
            }
        }
        metadata = {}
        # patch ifconfig -a
        with mock.patch(
            "cloudinit.distros.networking.subp.subp", return_value=("", None)
        ):
            cloud = self.tmp_cloud(
                distro="freebsd", sys_cfg=sys_cfg, metadata=metadata
            )
        cc_users_groups.handle("modulename", cfg, cloud, None)
        self.assertCountEqual(
            m_fbsd_user.call_args_list,
            [
                mock.call(
                    "freebsd",
                    groups="wheel",
                    lock_passwd=True,
                    shell="/bin/tcsh",
                    homedir="/home/freebsd",
                ),
                mock.call("me2", uid=1234, default=False),
            ],
        )
        m_fbsd_group.assert_not_called()
        m_linux_group.assert_not_called()
        m_linux_user.assert_not_called()

    def test_users_with_ssh_redirect_user_passes_keys(self, m_user, m_group):
        """When ssh_redirect_user is True pass default user and cloud keys."""
        cfg = {
            "users": ["default", {"name": "me2", "ssh_redirect_user": True}]
        }
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {"public-keys": ["key1"]}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None)
        self.assertCountEqual(
            m_user.call_args_list,
            [
                mock.call(
                    "ubuntu",
                    groups="lxd,sudo",
                    lock_passwd=True,
                    shell="/bin/bash",
                ),
                mock.call(
                    "me2",
                    cloud_public_ssh_keys=["key1"],
                    default=False,
                    ssh_redirect_user="ubuntu",
                ),
            ],
        )
        m_group.assert_not_called()

    def test_users_with_ssh_redirect_user_default_str(self, m_user, m_group):
        """When ssh_redirect_user is 'default' pass default username."""
        cfg = {
            "users": [
                "default",
                {"name": "me2", "ssh_redirect_user": "default"},
            ]
        }
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {"public-keys": ["key1"]}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None)
        self.assertCountEqual(
            m_user.call_args_list,
            [
                mock.call(
                    "ubuntu",
                    groups="lxd,sudo",
                    lock_passwd=True,
                    shell="/bin/bash",
                ),
                mock.call(
                    "me2",
                    cloud_public_ssh_keys=["key1"],
                    default=False,
                    ssh_redirect_user="ubuntu",
                ),
            ],
        )
        m_group.assert_not_called()

    def test_users_without_home_cannot_import_ssh_keys(self, m_user, m_group):
        cfg = {
            "users": [
                "default",
                {
                    "name": "me2",
                    "ssh_import_id": ["snowflake"],
                    "no_create_home": True,
                },
            ]
        }
        cloud = self.tmp_cloud(distro="ubuntu", sys_cfg={}, metadata={})
        with self.assertRaises(ValueError) as context_manager:
            cc_users_groups.handle("modulename", cfg, cloud, None)
        m_group.assert_not_called()
        self.assertEqual(
            "Not creating user me2. Key(s) ssh_import_id cannot be provided"
            " with no_create_home",
            str(context_manager.exception),
        )

    def test_users_with_ssh_redirect_user_non_default(self, m_user, m_group):
        """Warn when ssh_redirect_user is not 'default'."""
        cfg = {
            "users": [
                "default",
                {"name": "me2", "ssh_redirect_user": "snowflake"},
            ]
        }
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {"public-keys": ["key1"]}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        with self.assertRaises(ValueError) as context_manager:
            cc_users_groups.handle("modulename", cfg, cloud, None)
        m_group.assert_not_called()
        self.assertEqual(
            "Not creating user me2. Invalid value of ssh_redirect_user:"
            " snowflake. Expected values: true, default or false.",
            str(context_manager.exception),
        )

    def test_users_with_ssh_redirect_user_default_false(self, m_user, m_group):
        """When unspecified ssh_redirect_user is false and not set up."""
        cfg = {"users": ["default", {"name": "me2"}]}
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {"public-keys": ["key1"]}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None)
        self.assertCountEqual(
            m_user.call_args_list,
            [
                mock.call(
                    "ubuntu",
                    groups="lxd,sudo",
                    lock_passwd=True,
                    shell="/bin/bash",
                ),
                mock.call("me2", default=False),
            ],
        )
        m_group.assert_not_called()

    def test_users_ssh_redirect_user_and_no_default(self, m_user, m_group):
        """Warn when ssh_redirect_user is True and no default user present."""
        cfg = {
            "users": ["default", {"name": "me2", "ssh_redirect_user": True}]
        }
        # System config defines *no* default user for the distro.
        sys_cfg = {}
        metadata = {}  # no public-keys defined
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None)
        m_user.assert_called_once_with("me2", default=False)
        m_group.assert_not_called()
        self.assertEqual(
            "WARNING: Ignoring ssh_redirect_user: True for me2. No"
            " default_user defined. Perhaps missing"
            " cloud configuration users:  [default, ..].\n",
            self.logs.getvalue(),
        )


class TestUsersGroupsSchema:
    @pytest.mark.parametrize(
        "config, expectation, has_errors",
        [
            # Validate default settings not covered by examples
            ({"groups": ["anygrp"]}, does_not_raise(), None),
            (
                {"groups": "anygrp,anyothergroup"},
                does_not_raise(),
                None,
            ),  # DEPRECATED
            # Create anygrp with user1 as member
            ({"groups": [{"anygrp": "user1"}]}, does_not_raise(), None),
            # Create anygrp with user1 as member using object/string syntax
            ({"groups": {"anygrp": "user1"}}, does_not_raise(), None),
            # Create anygrp with user1 as member using object/list syntax
            ({"groups": {"anygrp": ["user1"]}}, does_not_raise(), None),
            (
                {"groups": [{"anygrp": ["user1", "user2"]}]},
                does_not_raise(),
                None,
            ),
            # Make default username "olddefault": DEPRECATED
            ({"user": "olddefault"}, does_not_raise(), None),
            # Create multiple users, and include default user. DEPRECATED
            ({"users": [{"name": "bbsw"}]}, does_not_raise(), None),
            (
                {"users": [{"name": "bbsw", "garbage-key": None}]},
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "users.0: {'name': 'bbsw', 'garbage-key': None} is"
                        " not of type 'string'"
                    ),
                ),
                True,
            ),
            (
                {"groups": {"": "bbsw"}},
                pytest.raises(
                    SchemaValidationError,
                    match="does not match any of the regexes",
                ),
                True,
            ),
            (
                {"users": [{"name": "bbsw", "groups": ["anygrp"]}]},
                does_not_raise(),
                None,
            ),  # user with a list of groups
            ({"groups": [{"yep": ["user1"]}]}, does_not_raise(), None),
            ({"users": "oldstyle,default"}, does_not_raise(), None),
            ({"users": ["default"]}, does_not_raise(), None),
            ({"users": ["default", ["aaa", "bbb"]]}, does_not_raise(), None),
            # no user creation at all
            ({"users": []}, does_not_raise(), None),
            # different default user creation
            ({"users": ["foobar"]}, does_not_raise(), None),
            (
                {"users": [{"name": "bbsw", "lock-passwd": True}]},
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "Cloud config schema deprecations: "
                        "users.0.lock-passwd:  Deprecated in version 22.3."
                        " Use ``lock_passwd`` instead."
                    ),
                ),
                False,
            ),
            (
                {"users": [{"name": "bbsw", "no-create-home": True}]},
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "Cloud config schema deprecations: "
                        "users.0.no-create-home:  Deprecated in version 24.2."
                        " Use ``no_create_home`` instead."
                    ),
                ),
                False,
            ),
            # users.groups supports comma-delimited str, list and object type
            (
                {"users": [{"name": "bbsw", "groups": "adm, sudo"}]},
                does_not_raise(),
                None,
            ),
            (
                {
                    "users": [
                        {"name": "bbsw", "groups": {"adm": None, "sudo": None}}
                    ]
                },
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "Cloud config schema deprecations: "
                        "users.0.groups.adm:  Deprecated in version 23.1. "
                        "The use of ``object`` type is deprecated. Use "
                        "``string`` or ``array`` of ``string`` instead., "
                        "users.0.groups.sudo:  Deprecated in version 23.1."
                    ),
                ),
                False,
            ),
            ({"groups": [{"yep": ["user1"]}]}, does_not_raise(), None),
            (
                {"user": ["no_list_allowed"]},
                pytest.raises(
                    SchemaValidationError,
                    match=re.escape(
                        "user: ['no_list_allowed'] is not of type 'string'"
                    ),
                ),
                True,
            ),
            (
                {"groups": {"anygrp": 1}},
                pytest.raises(
                    SchemaValidationError,
                    match="groups.anygrp: 1 is not of type 'string', 'array'",
                ),
                True,
            ),
            (
                {
                    "users": [{"inactive": True, "name": "cloudy"}],
                },
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "errors: users.0.inactive: True is not of type"
                        " 'string'"
                    ),
                ),
                True,
            ),
            (
                {
                    "users": [
                        {
                            "expiredate": "2038-01-19",
                            "groups": "users",
                            "name": "foobar",
                        }
                    ]
                },
                does_not_raise(),
                None,
            ),
            (
                {"user": {"name": "aciba", "groups": {"sbuild": None}}},
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "Cloud config schema deprecations: "
                        "user.groups.sbuild:  Deprecated in version 23.1."
                    ),
                ),
                False,
            ),
            (
                {"user": {"name": "mynewdefault", "sudo": False}},
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "Cloud config schema deprecations: user.sudo:"
                        "  Changed in version 22.2. The value "
                        "``false`` is deprecated for this key, use "
                        "``null`` instead."
                    ),
                ),
                False,
            ),
            (
                {"user": {"name": "mynewdefault", "sudo": None}},
                does_not_raise(),
                None,
            ),
            (
                {"users": [{"name": "a", "uid": "1743"}]},
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "Cloud config schema deprecations: "
                        "users.0.uid:  Changed in version 22.3. The "
                        "use of ``string`` type is deprecated. Use "
                        "an ``integer`` instead."
                    ),
                ),
                False,
            ),
            (
                {"users": [{"name": "a", "expiredate": "2038,1,19"}]},
                pytest.raises(
                    SchemaValidationError,
                    match=("users.0.expiredate: '2038,1,19' is not a 'date'"),
                ),
                True,
            ),
            (
                {
                    "users": [
                        {
                            "name": "lima",
                            "uid": "1000",
                            "homedir": "/home/lima.linux",
                            "shell": "/bin/bash",
                            "sudo": "ALL=(ALL) NOPASSWD:ALL",
                            "lock_passwd": True,
                            "ssh-authorized-keys": ["ssh-ed25519 ..."],
                        }
                    ]
                },
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "Cloud config schema deprecations: "
                        "users.0.ssh-authorized-keys: "
                        " Deprecated in version 18.3."
                        " Use ``ssh_authorized_keys`` instead."
                        ", "
                        "users.0.uid: "
                        " Changed in version 22.3."
                        " The use of ``string`` type is deprecated."
                        " Use an ``integer`` instead."
                    ),
                ),
                False,
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, expectation, has_errors):
        with expectation as exc_info:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
            if has_errors is not None:
                assert has_errors == exc_info.value.has_errors()
