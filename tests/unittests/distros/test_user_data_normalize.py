# This file is part of cloud-init. See LICENSE file for license information.
from unittest import mock

import pytest

from cloudinit import distros, helpers, settings
from cloudinit.distros import ug_util

bcfg = {
    "name": "bob",
    "plain_text_passwd": "ubuntu",
    "home": "/home/ubuntu",
    "shell": "/bin/bash",
    "lock_passwd": True,
    "gecos": "Ubuntu",
    "groups": ["foo"],
}


class TestUGNormalize:
    def _make_distro(self, dtype, def_user=None):
        cfg = dict(settings.CFG_BUILTIN)
        cfg["system_info"]["distro"] = dtype
        paths = helpers.Paths(cfg["system_info"]["paths"])
        distro_cls = distros.fetch(dtype)
        if def_user:
            cfg["system_info"]["default_user"] = def_user.copy()
        distro = distro_cls(dtype, cfg["system_info"], paths)
        return distro

    def _norm(self, cfg, distro):
        return ug_util.normalize_users_groups(cfg, distro)

    def test_group_dict(self):
        distro = self._make_distro("ubuntu")
        g = {
            "groups": [
                {"ubuntu": ["foo", "bar"], "bob": "users"},
                "cloud-users",
                {"bob": "users2"},
            ]
        }
        _users, groups = self._norm(g, distro)
        assert "ubuntu" in groups
        ub_members = groups["ubuntu"]
        assert sorted(["foo", "bar"]) == sorted(ub_members)
        assert "bob" in groups
        b_members = groups["bob"]
        assert sorted(["users", "users2"]) == sorted(b_members)

    def test_basic_groups(self):
        distro = self._make_distro("ubuntu")
        ug_cfg = {
            "groups": ["bob"],
        }
        users, groups = self._norm(ug_cfg, distro)
        assert "bob" in groups
        assert {} == users

    def test_csv_groups(self):
        distro = self._make_distro("ubuntu")
        ug_cfg = {
            "groups": "bob,joe,steve",
        }
        users, groups = self._norm(ug_cfg, distro)
        assert "bob" in groups
        assert "joe" in groups
        assert "steve" in groups
        assert {} == users

    def test_more_groups(self):
        distro = self._make_distro("ubuntu")
        ug_cfg = {"groups": ["bob", "joe", "steve"]}
        users, groups = self._norm(ug_cfg, distro)
        assert "bob" in groups
        assert "joe" in groups
        assert "steve" in groups
        assert {} == users

    def test_member_groups(self):
        distro = self._make_distro("ubuntu")
        ug_cfg = {
            "groups": {
                "bob": ["s"],
                "joe": [],
                "steve": [],
            }
        }
        users, groups = self._norm(ug_cfg, distro)
        assert "bob" in groups
        assert ["s"] == groups["bob"]
        assert [] == groups["joe"]
        assert "joe" in groups
        assert "steve" in groups
        assert {} == users

    @pytest.mark.parametrize(
        "ug_cfg",
        [
            {"users": {"default": True}},
            {"users": {"default": "yes"}},
            {"users": {"default": "1"}},
        ],
    )
    def test_users_simple_dict(self, ug_cfg):
        distro = self._make_distro("ubuntu", bcfg)
        users, _groups = self._norm(ug_cfg, distro)
        assert "bob" in users

    @pytest.mark.parametrize(
        "ug_cfg", [{"users": {"default": False}}, {"users": {"default": "no"}}]
    )
    def test_users_simple_dict_no(self, ug_cfg):
        distro = self._make_distro("ubuntu", bcfg)
        users, _groups = self._norm(ug_cfg, distro)
        assert {} == users

    def test_users_simple_csv(self):
        distro = self._make_distro("ubuntu")
        ug_cfg = {
            "users": "joe,bob",
        }
        users, _groups = self._norm(ug_cfg, distro)
        assert "joe" in users
        assert "bob" in users
        assert {"default": False} == users["joe"]
        assert {"default": False} == users["bob"]

    def test_users_simple(self):
        distro = self._make_distro("ubuntu")
        ug_cfg = {
            "users": ["joe", "bob"],
        }
        users, _groups = self._norm(ug_cfg, distro)
        assert "joe" in users
        assert "bob" in users
        assert {"default": False} == users["joe"]
        assert {"default": False} == users["bob"]
        users, _groups = self._norm({"users": []}, distro)
        assert {} == users

    def test_users_old_user(self):
        distro = self._make_distro("ubuntu", bcfg)
        ug_cfg = {"user": "zetta", "users": "default"}
        users, _groups = self._norm(ug_cfg, distro)
        assert "bob" not in users  # Bob is not the default now, zetta is
        assert "zetta" in users
        assert users["zetta"]["default"] is True
        assert "default" not in users
        ug_cfg = {"user": "zetta", "users": "default, joe"}
        users, _groups = self._norm(ug_cfg, distro)
        assert "bob" not in users  # Bob is not the default now, zetta is
        assert "joe" in users
        assert "zetta" in users
        assert users["zetta"]["default"] is True
        assert "default" not in users
        ug_cfg = {"user": "zetta", "users": ["bob", "joe"]}
        users, _groups = self._norm(ug_cfg, distro)
        assert "bob" in users
        assert "joe" in users
        assert "zetta" in users
        assert users["zetta"]["default"] is True
        ug_cfg = {
            "user": "zetta",
            "users": {
                "bob": True,
                "joe": True,
            },
        }
        users, _groups = self._norm(ug_cfg, distro)
        assert "bob" in users
        assert "joe" in users
        assert "zetta" in users
        assert users["zetta"]["default"] is True
        ug_cfg = {
            "user": "zetta",
        }
        users, _groups = self._norm(ug_cfg, distro)
        assert "zetta" in users
        ug_cfg = {}
        users, groups = self._norm(ug_cfg, distro)
        assert {} == users
        assert {} == groups

    def test_users_dict_default_additional(self):
        distro = self._make_distro("ubuntu", bcfg)
        ug_cfg = {
            "users": [{"name": "default", "blah": True}],
        }
        users, _groups = self._norm(ug_cfg, distro)
        assert "bob" in users
        assert (
            ",".join(distro.get_default_user()["groups"])
            == users["bob"]["groups"]
        )
        assert users["bob"]["blah"] is True
        assert users["bob"]["default"] is True

    def test_users_dict_extract(self):
        distro = self._make_distro("ubuntu", bcfg)
        ug_cfg = {
            "users": [
                "default",
            ],
        }
        users, _groups = self._norm(ug_cfg, distro)
        assert "bob" in users
        (name, config) = ug_util.extract_default(users)
        assert name == "bob"
        expected_config = {}
        def_config = None
        try:
            def_config = distro.get_default_user()
        except NotImplementedError:
            pass
        if not def_config:
            def_config = {}
        expected_config.update(def_config)

        # Ignore these for now
        expected_config.pop("name", None)
        expected_config.pop("groups", None)
        config.pop("groups", None)
        assert config == expected_config

    def test_users_dict_default(self):
        distro = self._make_distro("ubuntu", bcfg)
        ug_cfg = {
            "users": [
                "default",
            ],
        }
        users, _groups = self._norm(ug_cfg, distro)
        assert "bob" in users
        assert (
            ",".join(distro.get_default_user()["groups"])
            == users["bob"]["groups"]
        )
        assert users["bob"]["default"] is True

    def test_users_dict_trans(self):
        distro = self._make_distro("ubuntu")
        ug_cfg = {
            "users": [
                {"name": "joe", "tr-me": True},
                {"name": "bob"},
            ],
        }
        users, _groups = self._norm(ug_cfg, distro)
        assert "joe" in users
        assert "bob" in users
        assert {"tr_me": True, "default": False} == users["joe"]
        assert {"default": False} == users["bob"]

    def test_users_dict(self):
        distro = self._make_distro("ubuntu")
        ug_cfg = {
            "users": [
                {"name": "joe"},
                {"name": "bob"},
            ],
        }
        users, _groups = self._norm(ug_cfg, distro)
        assert "joe" in users
        assert "bob" in users
        assert {"default": False} == users["joe"]
        assert {"default": False} == users["bob"]

    @mock.patch("cloudinit.subp.subp")
    def test_create_snap_user(self, mock_subp):
        mock_subp.side_effect = [
            ('{"username": "joe", "ssh-key-count": 1}\n', "")
        ]
        distro = self._make_distro("ubuntu")
        ug_cfg = {
            "users": [
                {"name": "joe", "snapuser": "joe@joe.com"},
            ],
        }
        users, _groups = self._norm(ug_cfg, distro)
        for user, config in users.items():
            print("user=%s config=%s" % (user, config))
            username = distro.create_user(user, **config)

        snapcmd = ["snap", "create-user", "--sudoer", "--json", "joe@joe.com"]
        mock_subp.assert_called_with(snapcmd, capture=True, logstring=snapcmd)
        assert username == "joe"

    @mock.patch("cloudinit.subp.subp")
    def test_create_snap_user_known(self, mock_subp):
        mock_subp.side_effect = [
            ('{"username": "joe", "ssh-key-count": 1}\n', "")
        ]
        distro = self._make_distro("ubuntu")
        ug_cfg = {
            "users": [
                {"name": "joe", "snapuser": "joe@joe.com", "known": True},
            ],
        }
        users, _groups = self._norm(ug_cfg, distro)
        for user, config in users.items():
            print("user=%s config=%s" % (user, config))
            username = distro.create_user(user, **config)

        snapcmd = [
            "snap",
            "create-user",
            "--sudoer",
            "--json",
            "--known",
            "joe@joe.com",
        ]
        mock_subp.assert_called_with(snapcmd, capture=True, logstring=snapcmd)
        assert username == "joe"

    @mock.patch("cloudinit.util.system_is_snappy")
    @mock.patch("cloudinit.util.is_group")
    @mock.patch("cloudinit.subp.subp")
    def test_add_user_on_snappy_system(
        self, mock_subp, mock_isgrp, mock_snappy
    ):
        mock_isgrp.return_value = False
        mock_subp.return_value = True
        mock_snappy.return_value = True
        distro = self._make_distro("ubuntu")
        ug_cfg = {
            "users": [
                {"name": "joe", "groups": "users", "create_groups": True},
            ],
        }
        users, _groups = self._norm(ug_cfg, distro)
        for user, config in users.items():
            print("user=%s config=%s" % (user, config))
            distro.add_user(user, **config)

        groupcmd = ["groupadd", "users", "--extrausers"]
        addcmd = ["useradd", "joe", "--extrausers", "--groups", "users", "-m"]

        mock_subp.assert_any_call(groupcmd)
        mock_subp.assert_any_call(addcmd, logstring=addcmd)
