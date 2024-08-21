# This file is part of cloud-init. See LICENSE file for license information.
import datetime
import logging
import os.path
import random
import re
import string
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Type
from uuid import UUID

from pycloudlib import (
    EC2,
    GCE,
    IBM,
    OCI,
    Azure,
    LXDContainer,
    LXDVirtualMachine,
    Openstack,
    Qemu,
)
from pycloudlib.cloud import ImageType
from pycloudlib.ec2.instance import EC2Instance
from pycloudlib.lxd.cloud import _BaseLXD
from pycloudlib.lxd.instance import BaseInstance, LXDInstance

import cloudinit
from cloudinit.subp import ProcessExecutionError, subp
from tests.integration_tests import integration_settings
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.releases import CURRENT_RELEASE
from tests.integration_tests.util import emit_dots_on_travis

log = logging.getLogger("integration_testing")

DISTRO_TO_USERNAME = {
    "ubuntu": "ubuntu",
}


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


class IntegrationCloud(ABC):
    datasource: str

    def __init__(
        self,
        image_type: ImageType = ImageType.GENERIC,
        settings=integration_settings,
    ):
        self._image_type = image_type
        self.settings = settings
        self.cloud_instance = self._get_cloud_instance()
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

    def _get_initial_image(self, **kwargs) -> str:
        return CURRENT_RELEASE.image_id or self.cloud_instance.daily_image(
            CURRENT_RELEASE.series, **kwargs
        )

    def _maybe_wait(self, pycloudlib_instance, wait):
        if wait:
            try:
                pycloudlib_instance.wait()
            except Exception:
                pycloudlib_instance.delete()
                raise

    def _perform_launch(
        self, *, launch_kwargs, wait=True, **kwargs
    ) -> BaseInstance:
        pycloudlib_instance = self.cloud_instance.launch(**launch_kwargs)
        self._maybe_wait(pycloudlib_instance, wait)
        return pycloudlib_instance

    def launch(
        self,
        user_data=None,
        wait=True,
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
            pycloudlib_instance = self.cloud_instance.get_instance(
                self.settings.EXISTING_INSTANCE_ID
            )
            instance = self.get_instance(pycloudlib_instance, settings)
            return instance
        default_launch_kwargs = {
            "image_id": self.image_id,
            "user_data": user_data,
            "username": DISTRO_TO_USERNAME[CURRENT_RELEASE.os],
        }
        launch_kwargs = {**default_launch_kwargs, **launch_kwargs}
        display_launch_kwargs = deepcopy(launch_kwargs)
        if display_launch_kwargs.get("user_data") is not None:
            if "token" in display_launch_kwargs.get("user_data"):
                display_launch_kwargs["user_data"] = re.sub(
                    r"token: .*", "token: REDACTED", launch_kwargs["user_data"]
                )
        log.info(
            "Launching instance with launch_kwargs:\n%s",
            "\n".join(
                "{}={}".format(*item) for item in display_launch_kwargs.items()
            ),
        )

        with emit_dots_on_travis():
            pycloudlib_instance = self._perform_launch(
                wait=wait, launch_kwargs=launch_kwargs, **kwargs
            )
        log.info("Launched instance: %s", pycloudlib_instance)
        instance = self.get_instance(pycloudlib_instance, settings)
        if wait:
            # If we aren't waiting, we can't rely on command execution here
            log.info(
                "cloud-init version: %s",
                instance.execute("cloud-init --version"),
            )
            serial = instance.execute("grep serial /etc/cloud/build.info")
            if serial:
                log.info("image serial: %s", serial.split()[1])
        return instance

    def get_instance(
        self, cloud_instance, settings=integration_settings
    ) -> IntegrationInstance:
        return IntegrationInstance(self, cloud_instance, settings)

    def destroy(self):
        if self.settings.KEEP_IMAGE or self.settings.KEEP_INSTANCE:
            log.info(
                "NOT cleaning cloud instance because KEEP_IMAGE or "
                "KEEP_INSTANCE is True"
            )
        else:
            self.cloud_instance.clean()

    def snapshot(self, instance):
        return self.cloud_instance.snapshot(instance, clean=True)

    def delete_snapshot(self):
        if self.snapshot_id:
            if self.settings.KEEP_IMAGE:  # type: ignore
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

    def _get_cloud_instance(self) -> EC2:
        return EC2(tag="ec2-integration-test")

    def _get_initial_image(self, **kwargs) -> str:
        return super()._get_initial_image(
            image_type=self._image_type, **kwargs
        )

    def _perform_launch(
        self, *, launch_kwargs, wait=True, enable_ipv6=True, **kwargs
    ) -> EC2Instance:
        """Use a dual-stack VPC for cloud-init integration testing."""
        if enable_ipv6:
            if "vpc" not in launch_kwargs:
                launch_kwargs["vpc"] = self.cloud_instance.get_or_create_vpc(
                    name="ec2-cloud-init-integration"
                )

        pycloudlib_instance = self.cloud_instance.launch(
            enable_ipv6=enable_ipv6, **launch_kwargs
        )
        self._maybe_wait(pycloudlib_instance, wait)
        return pycloudlib_instance


class GceCloud(IntegrationCloud):
    datasource = "gce"

    def _get_cloud_instance(self) -> GCE:
        return GCE(
            tag="gce-integration-test",
        )

    def _get_initial_image(self, **kwargs) -> str:
        return super()._get_initial_image(
            image_type=self._image_type, **kwargs
        )


class AzureCloud(IntegrationCloud):
    datasource = "azure"
    cloud_instance: Azure

    def _get_cloud_instance(self) -> Azure:
        return Azure(tag="azure-integration-test")

    def _get_initial_image(self, **kwargs) -> str:
        return super()._get_initial_image(
            image_type=self._image_type, **kwargs
        )

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

    def _get_cloud_instance(self) -> OCI:
        return OCI(
            tag="oci-integration-test",
        )


class _LxdIntegrationCloud(IntegrationCloud):
    pycloudlib_instance_cls: Type[_BaseLXD]
    instance_tag: str
    cloud_instance: _BaseLXD

    def _get_or_set_profile_list(self, release):
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
            (
                os.path.join(cloudinit_path, "..", "doc", "module-docs"),
                "/usr/share/doc/cloud-init/module-docs",
            ),
        ]
        for n, (source_path, target_path) in enumerate(mounts):
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

    def _perform_launch(
        self, *, launch_kwargs, wait=True, **kwargs
    ) -> LXDInstance:
        instance_kwargs = deepcopy(launch_kwargs)
        instance_kwargs["inst_type"] = instance_kwargs.pop(
            "instance_type", None
        )
        release = instance_kwargs.pop("image_id")

        try:
            profile_list = instance_kwargs["profile_list"]
        except KeyError:
            profile_list = self._get_or_set_profile_list(release)

        prefix = datetime.datetime.utcnow().strftime("cloudinit-%m%d-%H%M%S")
        default_name = prefix + "".join(
            random.choices(string.ascii_lowercase + string.digits, k=8)
        )
        pycloudlib_instance = self.cloud_instance.init(
            instance_kwargs.pop("name", default_name),
            release,
            profile_list=profile_list,
            **instance_kwargs,
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

    def _get_cloud_instance(self) -> LXDContainer:
        return self.pycloudlib_instance_cls(tag=self.instance_tag)


class LxdVmCloud(_LxdIntegrationCloud):
    datasource = "lxd_vm"
    cloud_instance: LXDVirtualMachine
    pycloudlib_instance_cls = LXDVirtualMachine
    instance_tag = "lxd-vm-integration-test"
    _profile_list: list = []

    def _get_cloud_instance(self) -> LXDVirtualMachine:
        return self.pycloudlib_instance_cls(tag=self.instance_tag)

    def _get_or_set_profile_list(self, release) -> list:
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

    def _get_initial_image(self, **kwargs):
        try:
            UUID(CURRENT_RELEASE.image_id)
        except ValueError as e:
            raise RuntimeError(
                "When using Openstack, `OS_IMAGE` MUST be specified with "
                "a 36-character UUID image ID. Passing in a release name is "
                "not valid here.\n"
                "OS image id: {}".format(CURRENT_RELEASE.image_id)
            ) from e
        return CURRENT_RELEASE.image_id


class IbmCloud(IntegrationCloud):
    datasource = "ibm"
    cloud_instance: IBM

    def _get_cloud_instance(self) -> IBM:
        # Note: IBM image names starting with `ibm` are reserved.
        return IBM(
            tag="integration-test-ibm",
        )


class QemuCloud(IntegrationCloud):
    datasource = "qemu"
    cloud_instance = Qemu

    def _get_cloud_instance(self):
        return Qemu(tag="qemu-integration-test")
