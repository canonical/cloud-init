# This file is part of cloud-init. See LICENSE file for license information.
import pytest

from tests.integration_tests.clouds import ImageSpecification
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_ordered_items_in_text


USER_DATA = """\
## template: jinja
#cloud-config
runcmd:
  - echo {{v1.local_hostname}} > /var/tmp/runcmd_output
  - echo {{merged_cfg._doc}} >> /var/tmp/runcmd_output'
"""


@pytest.mark.user_data(USER_DATA)
def test_runcmd_with_variable_substitution(client: IntegrationInstance):
    """Test jinja substitution.

    Ensure we can also substitue variables from instance-data-sensitive
    LP: #1931392
    """
    expected = [
        client.execute('hostname').stdout.strip(),
        ('Merged cloud-init system config from /etc/cloud/cloud.cfg and '
            '/etc/cloud/cloud.cfg.d/')
    ]
    output = client.read_from_file('/var/tmp/runcmd_output')
    verify_ordered_items_in_text(expected, output)
