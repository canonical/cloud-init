import logging

import pytest

LOG = logging.getLogger("integration_testing.test_utility")


class TestUtilities:
    @pytest.mark.instance_name("boot")
    def test_boot(self, client):
        """Boot an instance. That's all it does."""
        assert client.execute("whoami").ok
        LOG.info('Instance name "boot" started')
