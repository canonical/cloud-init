# This file is part of cloud-init. See LICENSE file for license information.
import datetime
import logging
import os.path
import random
import string
from abc import ABC, abstractmethod
from typing import Optional, Type
from uuid import UUID

from pycloudlib import (
    EC2,
    GCE,
    OCI,
    Azure,
    LXDContainer,
    LXDVirtualMachine,
    Openstack,
)
from pycloudlib.cloud import BaseCloud
from pycloudlib.lxd.cloud import _BaseLXD
from pycloudlib.lxd.instance import LXDInstance

import cloudinit
from cloudinit.subp import ProcessExecutionError, subp
from tests.integration_tests import integration_settings
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import emit_dots_on_travis

log = logging.getLogger("integration_testing")


def _get_ubuntu_series() -> list:
    """Use distro-info-data's ubuntu.csv to get a list of Ubuntu series"""
    out = ""
    try:
        out, _err = subp(["ubuntu-distro-info", "-a"])
    except ProcessExecutionError:
        log.info(
            "ubuntu-distro-info (from the distro-info package) must be"
            " installed to guess Ubuntu os/release"
        )
    return out.splitlines()


class ImageSpecification:
    """A specification of an image to launch for testing.

    If either of ``os`` and ``release`` are not specified, an attempt will be
    made to infer the correct values for these on instantiation.

    :param image_id:
        The image identifier used by the rest of the codebase to launch this
        image.
    :param os:
        An optional string describing the operating system this image is for
        (e.g.  "ubuntu", "rhel", "freebsd").
    :param release:
        A optional string describing the operating system release (e.g.
        "focal", "8"; the exact values here will depend on the OS).
    """

    def __init__(
        self,
        image_id: str,
        os: Optional[str] = None,
        release: Optional[str] = None,
    ):
        if image_id in _get_ubuntu_series():
            if os is None:
                os = "ubuntu"
            if release is None:
                release = image_id

        self.image_id = image_id
        self.os = os
        self.release = release
        log.info(
            "Detected image: image_id=%s os=%s release=%s",
            self.image_id,
            self.os,
            self.release,
        )

    @classmethod
    def from_os_image(cls):
        """Return an ImageSpecification for integration_settings.OS_IMAGE."""
        parts = integration_settings.OS_IMAGE.split("::", 2)
        return cls(*parts)


class IntegrationCloud(ABC):
    datasource: str
    cloud_instance: BaseCloud

    def __init__(self, settings=integration_settings):
        self.settings = settings
        self.cloud_instance: BaseCloud = self._get_cloud_instance()
        self.initial_image_id = self._get_initial_image()
        self.snapshot_id = None

    @property
    def image_id(self):
        return self.snapshot_id or self.initial_image_id

    def emit_settings_to_log(self) -> None:
        log.info(
            "\n".join(
                ["Settings:"]
                + [
                    "{}={}".format(key, getattr(self.settings, key))
                    for key in sorted(self.settings.current_settings)
                ]
            )
        )

    @abstractmethod
    def _get_cloud_instance(self):
        raise NotImplementedError

    def _get_initial_image(self):
        image = ImageSpecification.from_os_image()
        try:
            return self.cloud_instance.daily_image(image.image_id)
        except (ValueError, IndexError):
            return image.image_id

    def _perform_launch(self, launch_kwargs, **kwargs):
        pycloudlib_instance = self.cloud_instance.launch(**launch_kwargs)
        return pycloudlib_instance

    def launch(
        self,
        user_data=None,
        launch_kwargs=None,
        settings=integration_settings,
        **kwargs,
    ) -> IntegrationInstance:
        if launch_kwargs is None:
            launch_kwargs = {}
        if self.settings.EXISTING_INSTANCE_ID:
            log.info(
                "Not launching instance due to EXISTING_INSTANCE_ID. "
                "Instance id: %s",
                self.settings.EXISTING_INSTANCE_ID,
            )
            self.instance = self.cloud_instance.get_instance(
                self.settings.EXISTING_INSTANCE_ID
            )
            return self.instance
        default_launch_kwargs = {
            "image_id": self.image_id,
            "user_data": user_data,
        }
        launch_kwargs = {**default_launch_kwargs, **launch_kwargs}
        log.info(
            "Launching instance with launch_kwargs:\n%s",
            "\n".join("{}={}".format(*item) for item in launch_kwargs.items()),
        )

        with emit_dots_on_travis():
            pycloudlib_instance = self._perform_launch(launch_kwargs, **kwargs)
        log.info("Launched instance: %s", pycloudlib_instance)
        instance = self.get_instance(pycloudlib_instance, settings)
        if launch_kwargs.get("wait", True):
            # If we aren't waiting, we can't rely on command execution here
            log.info(
                "cloud-init version: %s",
                instance.execute("cloud-init --version"),
            )
            serial = instance.execute("grep serial /etc/cloud/build.info")
            if serial:
                log.info("image serial: %s", serial.split()[1])
        return instance

    def get_instance(self, cloud_instance, settings=integration_settings):
        return IntegrationInstance(self, cloud_instance, settings)

    def destroy(self):
        pass

    def snapshot(self, instance):
        return self.cloud_instance.snapshot(instance, clean=True)

    def delete_snapshot(self):
        if self.snapshot_id:
            if self.settings.KEEP_IMAGE:
                log.info(
                    "NOT deleting snapshot image created for this testrun "
                    "because KEEP_IMAGE is True: %s",
                    self.snapshot_id,
                )
            else:
                log.info(
                    "Deleting snapshot image created for this testrun: %s",
                    self.snapshot_id,
                )
                self.cloud_instance.delete_image(self.snapshot_id)


class Ec2Cloud(IntegrationCloud):
    datasource = "ec2"

    def _get_cloud_instance(self):
        return EC2(tag="ec2-integration-test")


class GceCloud(IntegrationCloud):
    datasource = "gce"

    def _get_cloud_instance(self):
        return GCE(
            tag="gce-integration-test",
        )


class AzureCloud(IntegrationCloud):
    datasource = "azure"
    cloud_instance: Azure

    def _get_cloud_instance(self):
        return Azure(tag="azure-integration-test")

    def destroy(self):
        if self.settings.KEEP_INSTANCE:
            log.info(
                "NOT deleting resource group because KEEP_INSTANCE is true "
                "and deleting resource group would also delete instance. "
                "Instance and resource group must both be manually deleted."
            )
        else:
            self.cloud_instance.delete_resource_group()


class OciCloud(IntegrationCloud):
    datasource = "oci"

    def _get_cloud_instance(self):
        return OCI(
            tag="oci-integration-test",
        )


class _LxdIntegrationCloud(IntegrationCloud):
    pycloudlib_instance_cls: Type[_BaseLXD]
    instance_tag: str
    cloud_instance: _BaseLXD

    def _get_cloud_instance(self):
        return self.pycloudlib_instance_cls(tag=self.instance_tag)

    @staticmethod
    def _get_or_set_profile_list(release):
        return None

    @staticmethod
    def _mount_source(instance: LXDInstance):
        cloudinit_path = cloudinit.__path__[0]
        mounts = [
            (cloudinit_path, "/usr/lib/python3/dist-packages/cloudinit"),
            (
                os.path.join(cloudinit_path, "..", "templates"),
                "/etc/cloud/templates",
            ),
        ]
        for (n, (source_path, target_path)) in enumerate(mounts):
            format_variables = {
                "name": instance.name,
                "source_path": os.path.realpath(source_path),
                "container_path": target_path,
                "idx": n,
            }
            log.info(
                "Mounting source %(source_path)s directly onto LXD"
                " container/VM named %(name)s at %(container_path)s",
                format_variables,
            )
            command = (
                "lxc config device add {name} host-cloud-init-{idx} disk "
                "source={source_path} "
                "path={container_path}"
            ).format(**format_variables)
            subp(command.split())

    def _perform_launch(self, launch_kwargs, **kwargs):
        launch_kwargs["inst_type"] = launch_kwargs.pop("instance_type", None)
        wait = launch_kwargs.pop("wait", True)
        release = launch_kwargs.pop("image_id")

        try:
            profile_list = launch_kwargs["profile_list"]
        except KeyError:
            profile_list = self._get_or_set_profile_list(release)

        prefix = datetime.datetime.utcnow().strftime("cloudinit-%m%d-%H%M%S")
        default_name = prefix + "".join(
            random.choices(string.ascii_lowercase + string.digits, k=8)
        )
        pycloudlib_instance = self.cloud_instance.init(
            launch_kwargs.pop("name", default_name),
            release,
            profile_list=profile_list,
            **launch_kwargs,
        )
        if self.settings.CLOUD_INIT_SOURCE == "IN_PLACE":
            self._mount_source(pycloudlib_instance)
        if "lxd_setup" in kwargs:
            log.info("Running callback specified by 'lxd_setup' mark")
            kwargs["lxd_setup"](pycloudlib_instance)
        pycloudlib_instance.start(wait=wait)
        return pycloudlib_instance


class LxdContainerCloud(_LxdIntegrationCloud):
    datasource = "lxd_container"
    cloud_instance: LXDContainer
    pycloudlib_instance_cls = LXDContainer
    instance_tag = "lxd-container-integration-test"


class LxdVmCloud(_LxdIntegrationCloud):
    datasource = "lxd_vm"
    cloud_instance: LXDVirtualMachine
    pycloudlib_instance_cls = LXDVirtualMachine
    instance_tag = "lxd-vm-integration-test"
    _profile_list = None

    def _get_or_set_profile_list(self, release):
        if self._profile_list:
            return self._profile_list
        self._profile_list = self.cloud_instance.build_necessary_profiles(
            release
        )
        return self._profile_list


class OpenstackCloud(IntegrationCloud):
    datasource = "openstack"

    def _get_cloud_instance(self):
        return Openstack(
            tag="openstack-integration-test",
        )

    def _get_initial_image(self):
        image = ImageSpecification.from_os_image()
        try:
            UUID(image.image_id)
        except ValueError as e:
            raise Exception(
                "When using Openstack, `OS_IMAGE` MUST be specified with "
                "a 36-character UUID image ID. Passing in a release name is "
                "not valid here.\n"
                "OS image id: {}".format(image.image_id)
            ) from e
        return image.image_id
