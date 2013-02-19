from mocker import MockerTestCase

from cloudinit import distros
from cloudinit import helpers
from cloudinit import settings

bcfg = {
   'name': 'bob',
   'plain_text_passwd': 'ubuntu',
   'home': "/home/ubuntu",
   'shell': "/bin/bash",
   'lock_passwd': True,
   'gecos': "Ubuntu",
   'groups': ["foo"]
}


class TestUGNormalize(MockerTestCase):

    def _make_distro(self, dtype, def_user=None):
        cfg = dict(settings.CFG_BUILTIN)
        cfg['system_info']['distro'] = dtype
        paths = helpers.Paths(cfg['system_info']['paths'])
        distro_cls = distros.fetch(dtype)
        if def_user:
            cfg['system_info']['default_user'] = def_user.copy()
        distro = distro_cls(dtype, cfg['system_info'], paths)
        return distro

    def _norm(self, cfg, distro):
        return distros.normalize_users_groups(cfg, distro)

    def test_group_dict(self):
        distro = self._make_distro('ubuntu')
        g = {'groups': [
                {
                    'ubuntu': ['foo', 'bar'],
                    'bob': 'users',
                },
                'cloud-users',
                {
                    'bob': 'users2',
                },
            ]
        }
        (_users, groups) = self._norm(g, distro)
        self.assertIn('ubuntu', groups)
        ub_members = groups['ubuntu']
        self.assertEquals(sorted(['foo', 'bar']), sorted(ub_members))
        self.assertIn('bob', groups)
        b_members = groups['bob']
        self.assertEquals(sorted(['users', 'users2']),
                          sorted(b_members))

    def test_basic_groups(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'groups': ['bob'],
        }
        (users, groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', groups)
        self.assertEquals({}, users)

    def test_csv_groups(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'groups': 'bob,joe,steve',
        }
        (users, groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', groups)
        self.assertIn('joe', groups)
        self.assertIn('steve', groups)
        self.assertEquals({}, users)

    def test_more_groups(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'groups': ['bob', 'joe', 'steve']
        }
        (users, groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', groups)
        self.assertIn('joe', groups)
        self.assertIn('steve', groups)
        self.assertEquals({}, users)

    def test_member_groups(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'groups': {
                'bob': ['s'],
                'joe': [],
                'steve': [],
            }
        }
        (users, groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', groups)
        self.assertEquals(['s'], groups['bob'])
        self.assertEquals([], groups['joe'])
        self.assertIn('joe', groups)
        self.assertIn('steve', groups)
        self.assertEquals({}, users)

    def test_users_simple_dict(self):
        distro = self._make_distro('ubuntu', bcfg)
        ug_cfg = {
            'users': {
                'default': True,
            }
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', users)
        ug_cfg = {
            'users': {
                'default': 'yes',
            }
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', users)
        ug_cfg = {
            'users': {
                'default': '1',
            }
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', users)

    def test_users_simple_dict_no(self):
        distro = self._make_distro('ubuntu', bcfg)
        ug_cfg = {
            'users': {
                'default': False,
            }
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertEquals({}, users)
        ug_cfg = {
            'users': {
                'default': 'no',
            }
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertEquals({}, users)

    def test_users_simple_csv(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'users': 'joe,bob',
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('joe', users)
        self.assertIn('bob', users)
        self.assertEquals({'default': False}, users['joe'])
        self.assertEquals({'default': False}, users['bob'])

    def test_users_simple(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'users': [
                'joe',
                'bob'
            ],
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('joe', users)
        self.assertIn('bob', users)
        self.assertEquals({'default': False}, users['joe'])
        self.assertEquals({'default': False}, users['bob'])

    def test_users_old_user(self):
        distro = self._make_distro('ubuntu', bcfg)
        ug_cfg = {
            'user': 'zetta',
            'users': 'default'
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertNotIn('bob', users)  # Bob is not the default now, zetta is
        self.assertIn('zetta', users)
        self.assertTrue(users['zetta']['default'])
        self.assertNotIn('default', users)
        ug_cfg = {
            'user': 'zetta',
            'users': 'default, joe'
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertNotIn('bob', users)  # Bob is not the default now, zetta is
        self.assertIn('joe', users)
        self.assertIn('zetta', users)
        self.assertTrue(users['zetta']['default'])
        self.assertNotIn('default', users)
        ug_cfg = {
            'user': 'zetta',
            'users': ['bob', 'joe']
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', users)
        self.assertIn('joe', users)
        self.assertIn('zetta', users)
        self.assertTrue(users['zetta']['default'])
        ug_cfg = {
            'user': 'zetta',
            'users': {
                'bob': True,
                'joe': True,
            }
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', users)
        self.assertIn('joe', users)
        self.assertIn('zetta', users)
        self.assertTrue(users['zetta']['default'])
        ug_cfg = {
            'user': 'zetta',
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('zetta', users)
        ug_cfg = {}
        (users, groups) = self._norm(ug_cfg, distro)
        self.assertEquals({}, users)
        self.assertEquals({}, groups)

    def test_users_dict_default_additional(self):
        distro = self._make_distro('ubuntu', bcfg)
        ug_cfg = {
            'users': [
                {'name': 'default', 'blah': True}
            ],
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', users)
        self.assertEquals(",".join(distro.get_default_user()['groups']),
                          users['bob']['groups'])
        self.assertEquals(True,
                          users['bob']['blah'])
        self.assertEquals(True,
                          users['bob']['default'])

    def test_users_dict_extract(self):
        distro = self._make_distro('ubuntu', bcfg)
        ug_cfg = {
            'users': [
                'default',
            ],
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', users)
        (name, config) = distros.extract_default(users)
        self.assertEquals(name, 'bob')
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
        expected_config.pop('name', None)
        expected_config.pop('groups', None)
        config.pop('groups', None)
        self.assertEquals(config, expected_config)

    def test_users_dict_default(self):
        distro = self._make_distro('ubuntu', bcfg)
        ug_cfg = {
            'users': [
                'default',
            ],
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', users)
        self.assertEquals(",".join(distro.get_default_user()['groups']),
                          users['bob']['groups'])
        self.assertEquals(True,
                          users['bob']['default'])

    def test_users_dict_trans(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'users': [
                {'name': 'joe',
                 'tr-me': True},
                {'name': 'bob'},
            ],
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('joe', users)
        self.assertIn('bob', users)
        self.assertEquals({'tr_me': True, 'default': False}, users['joe'])
        self.assertEquals({'default': False}, users['bob'])

    def test_users_dict(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'users': [
                {'name': 'joe'},
                {'name': 'bob'},
            ],
        }
        (users, _groups) = self._norm(ug_cfg, distro)
        self.assertIn('joe', users)
        self.assertIn('bob', users)
        self.assertEquals({'default': False}, users['joe'])
        self.assertEquals({'default': False}, users['bob'])
