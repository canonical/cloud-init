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

from tests.integration_tests.instances import (
    CloudInstance,
    Ec2Instance,
    GceInstance,
    AzureInstance,
    OciInstance,
    LxdContainerInstance,
)

platform = namedtuple('Platform', 'cloud instance')
platforms = {
    'ec2': platform(Ec2Cloud, Ec2Instance),
    'gce': platform(GceCloud, GceInstance),
    'azure': platform(AzureCloud, AzureInstance),
    'oci': platform(OciCloud, OciInstance),
    'lxd_container': platform(LxdContainerCloud, LxdContainerInstance),
}

if integration_settings.PLATFORM not in platforms.keys():
    raise ValueError(
        "{} is an invalid PLATFORM specified in settings. "
        "Must be one of {}".format(
            integration_settings.PLATFORM, list(platforms.keys())
        )
    )


_session_cloud = None
_dynamic_instance = None


def initialize_session_client():
    global _session_cloud
    global _dynamic_instance

    if _session_cloud or _dynamic_instance:
        raise Exception("initialize_session_client() called more than once")

    dynamic_platform = platforms[integration_settings.PLATFORM]
    _session_cloud = dynamic_platform.cloud()
    _dynamic_instance = dynamic_platform.instance


def session_cloud() -> IntegrationCloud:
    if _session_cloud is None:
        raise Exception("Call initialize_session_client() first")
    return _session_cloud


def dynamic_instance(**kwargs) -> CloudInstance:
    if _dynamic_instance is None:
        raise Exception("Call initialize_session_client() first")
    return _dynamic_instance(_session_cloud, **kwargs)
