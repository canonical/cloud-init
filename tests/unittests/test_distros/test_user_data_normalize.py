from mocker import MockerTestCase

from cloudinit import distros
from cloudinit import helpers
from cloudinit import settings


class TestUGNormalize(MockerTestCase):

    def _make_distro(self, dtype, def_user=None, def_groups=None):
        cfg = dict(settings.CFG_BUILTIN)
        cfg['system_info']['distro'] = dtype
        paths = helpers.Paths(cfg['system_info']['paths'])
        distro_cls = distros.fetch(dtype)
        distro = distro_cls(dtype, cfg['system_info'], paths)
        if def_user:
            distro.default_user = def_user
        if def_groups:
            distro.default_user_groups = def_groups
        return distro

    def _norm(self, cfg, distro):
        def_u = distro.get_default_user()
        def_u_gs = distro.get_default_user_groups()
        return distros.normalize_users_groups(cfg, def_u, def_u_gs)

    def test_basic_groups(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'groups': ['bob'],
        }
        ((users, def_user), groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', groups)
        self.assertEquals({}, users)
        self.assertEquals({}, def_user)

    def test_csv_groups(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'groups': 'bob,joe,steve',
        }
        ((users, def_user), groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', groups)
        self.assertIn('joe', groups)
        self.assertIn('steve', groups)
        self.assertEquals({}, users)
        self.assertEquals({}, def_user)

    def test_more_groups(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'groups': ['bob', 'joe', 'steve',]
        }
        ((users, def_user), groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', groups)
        self.assertIn('joe', groups)
        self.assertIn('steve', groups)
        self.assertEquals({}, users)
        self.assertEquals({}, def_user)

    def test_member_groups(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'groups': {
                'bob': ['s'],
                'joe': [],
                'steve': [],
            }
        }
        ((users, def_user), groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', groups)
        self.assertEquals(['s'], groups['bob'])
        self.assertEquals([], groups['joe'])
        self.assertIn('joe', groups)
        self.assertIn('steve', groups)
        self.assertEquals({}, users)
        self.assertEquals({}, def_user)

    def test_users_simple_dict(self):
        distro = self._make_distro('ubuntu', 'bob')
        ug_cfg = {
            'users': {
                'default': True,
            }
        }
        ((_users, def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertEquals('bob', def_user['name'])
        ug_cfg = {
            'users': {
                'default': 'yes',
            }
        }
        ((_users, def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertEquals('bob', def_user['name'])
        ug_cfg = {
            'users': {
                'default': '1',
            }
        }
        ((_users, def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertEquals('bob', def_user['name'])

    def test_users_simple_dict_no(self):
        distro = self._make_distro('ubuntu', 'bob')
        ug_cfg = {
            'users': {
                'default': False,
            }
        }
        ((_users, def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertEquals({}, def_user)
        ug_cfg = {
            'users': {
                'default': 'no',
            }
        }
        ((_users, def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertEquals({}, def_user)

    def test_users_simple_csv(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'users': 'joe,bob',
        }
        ((users, _def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertIn('joe', users)
        self.assertIn('bob', users)
        self.assertEquals({}, users['joe'])
        self.assertEquals({}, users['bob'])

    def test_users_simple(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'users': [
                'joe',
                'bob'
            ],
        }
        ((users, _def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertIn('joe', users)
        self.assertIn('bob', users)
        self.assertEquals({}, users['joe'])
        self.assertEquals({}, users['bob'])

    def test_users_dict_default_additional(self):
        distro = self._make_distro('ubuntu', 'bob')
        ug_cfg = {
            'users': [
                {'name': 'default', 'blah': True}
            ],
        }
        ((users, def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', def_user['name'])
        self.assertEquals(",".join(distro.get_default_user_groups()),
                          def_user['config']['groups'])
        self.assertEquals(True,
                          def_user['config']['blah'])
        self.assertNotIn('bob', users)

    def test_users_dict_default(self):
        distro = self._make_distro('ubuntu', 'bob')
        ug_cfg = {
            'users': [
                'default',
            ],
        }
        ((users, def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertIn('bob', def_user['name'])
        self.assertEquals(",".join(distro.get_default_user_groups()),
                          def_user['config']['groups'])
        self.assertNotIn('bob', users)

    def test_users_dict_trans(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'users': [
                {'name': 'joe',
                 'tr-me': True},
                {'name': 'bob'},
            ],
        }
        ((users, _def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertIn('joe', users)
        self.assertIn('bob', users)
        self.assertEquals({'tr_me': True}, users['joe'])
        self.assertEquals({}, users['bob'])

    def test_users_dict(self):
        distro = self._make_distro('ubuntu')
        ug_cfg = {
            'users': [
                {'name': 'joe'},
                {'name': 'bob'},
            ],
        }
        ((users, _def_user), _groups) = self._norm(ug_cfg, distro)
        self.assertIn('joe', users)
        self.assertIn('bob', users)
        self.assertEquals({}, users['joe'])
        self.assertEquals({}, users['bob'])



