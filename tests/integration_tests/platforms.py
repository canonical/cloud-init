# This file is part of cloud-init. See LICENSE file for license information.
from collections import namedtuple

from tests.integration_tests import integration_settings
from tests.integration_tests.clouds import (
    IntegrationCloud,
    Ec2Cloud,
    GceCloud,
    AzureCloud,
    OciCloud,
    LxdContainerCloud,
)

platforms = {
    'ec2': Ec2Cloud,
    'gce': GceCloud,
    'azure': AzureCloud,
    'oci': OciCloud,
    'lxd_container': LxdContainerCloud,
}

if integration_settings.PLATFORM not in platforms.keys():
    raise ValueError(
        "{} is an invalid PLATFORM specified in settings. "
        "Must be one of {}".format(
            integration_settings.PLATFORM, list(platforms.keys())
        )
    )


_session_cloud = None


def session_cloud() -> IntegrationCloud:
    global _session_cloud
    if _session_cloud is None:
        _session_cloud = platforms[integration_settings.PLATFORM]()
    return _session_cloud
