from mocker import MockerTestCase

from cloudinit.cs_utils import Cepko


SERVER_CONTEXT = {
    "cpu": 1000,
    "cpus_instead_of_cores": False,
    "global_context": {"some_global_key": "some_global_val"},
    "mem": 1073741824,
    "meta": {"ssh_public_key": "ssh-rsa AAAAB3NzaC1yc2E.../hQ5D5 john@doe"},
    "name": "test_server",
    "requirements": [],
    "smp": 1,
    "tags": ["much server", "very performance"],
    "uuid": "65b2fb23-8c03-4187-a3ba-8b7c919e889",
    "vnc_password": "9e84d6cb49e46379"
}


class CepkoMock(Cepko):
    def all(self):
        return SERVER_CONTEXT

    def get(self, key="", request_pattern=None):
        return SERVER_CONTEXT['tags']


class CepkoResultTests(MockerTestCase):
    def setUp(self):
        self.mocked = self.mocker.replace("cloudinit.cs_utils.Cepko",
                            spec=CepkoMock,
                            count=False,
                            passthrough=False)
        self.mocked()
        self.mocker.result(CepkoMock())
        self.mocker.replay()
        self.c = Cepko()

    def test_getitem(self):
        result = self.c.all()
        self.assertEqual("65b2fb23-8c03-4187-a3ba-8b7c919e889", result['uuid'])
        self.assertEqual([], result['requirements'])
        self.assertEqual("much server", result['tags'][0])
        self.assertEqual(1, result['smp'])

    def test_len(self):
        self.assertEqual(len(SERVER_CONTEXT), len(self.c.all()))

    def test_contains(self):
        result = self.c.all()
        self.assertTrue('uuid' in result)
        self.assertFalse('uid' in result)
        self.assertTrue('meta' in result)
        self.assertFalse('ssh_public_key' in result)

    def test_iter(self):
        self.assertEqual(sorted(SERVER_CONTEXT.keys()),
                         sorted([key for key in self.c.all()]))

    def test_with_list_as_result(self):
        result = self.c.get('tags')
        self.assertEqual('much server', result[0])
        self.assertTrue('very performance' in result)
        self.assertEqual(2, len(result))
