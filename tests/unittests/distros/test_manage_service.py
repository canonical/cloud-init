# This file is part of cloud-init. See LICENSE file for license information.

from tests.unittests.helpers import CiTestCase, mock
from tests.unittests.util import MockDistro


class TestManageService(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestManageService, self).setUp()
        self.dist = MockDistro()

    @mock.patch.object(MockDistro, "uses_systemd", return_value=False)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_manage_service_systemctl_initcmd(self, m_subp, m_sysd):
        self.dist.init_cmd = ["systemctl"]
        self.dist.manage_service("start", "myssh")
        m_subp.assert_called_with(
            ["systemctl", "start", "myssh"], capture=True
        )

    @mock.patch.object(MockDistro, "uses_systemd", return_value=False)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_manage_service_service_initcmd(self, m_subp, m_sysd):
        self.dist.init_cmd = ["service"]
        self.dist.manage_service("start", "myssh")
        m_subp.assert_called_with(["service", "myssh", "start"], capture=True)

    @mock.patch.object(MockDistro, "uses_systemd", return_value=True)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_manage_service_systemctl(self, m_subp, m_sysd):
        self.dist.init_cmd = ["ignore"]
        self.dist.manage_service("start", "myssh")
        m_subp.assert_called_with(
            ["systemctl", "start", "myssh"], capture=True
        )


# vi: ts=4 sw=4 expandtab
