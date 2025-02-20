# This file is part of cloud-init. See LICENSE file for license information.

import pytest

from tests.integration_tests import releases
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.releases import IS_UBUNTU
from tests.integration_tests.util import ASSETS_DIR


@pytest.mark.skipif(
    not IS_UBUNTU, reason="module dir tested is ubuntu-specific"
)
def test_custom_module_24_1(client: IntegrationInstance):
    """Ensure that modifications to cloud-init don't break old custom modules.

    24.1 had documentation that differs from current best practices. We want
    to ensure modules created from this documentation still work:
    https://docs.cloud-init.io/en/24.1/development/module_creation.html
    """
    client.push_file(
        ASSETS_DIR / "dropins/cc_custom_module_24_1.py",
        "/usr/lib/python3/dist-packages/cloudinit/config/cc_custom_module_24_1.py",
    )
    output = client.execute("cloud-init single --name cc_custom_module_24_1")
    if releases.CURRENT_RELEASE >= releases.PLUCKY:
        assert "The 'get_meta_doc()' function is deprecated" in output
    assert "Hello from module" in output
