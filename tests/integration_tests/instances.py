# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
import re
import uuid
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Union

from pycloudlib.gce.instance import GceInstance
from pycloudlib.instance import BaseInstance
from pycloudlib.lxd.instance import LXDInstance
from pycloudlib.result import Result

from tests.helpers import cloud_init_project_dir
from tests.integration_tests import integration_settings
from tests.integration_tests.decorators import retry
from tests.integration_tests.util import ASSETS_DIR

try:
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from tests.integration_tests.clouds import (  # noqa: F401
            IntegrationCloud,
        )
except ImportError:
    pass


log = logging.getLogger("integration_testing")


def _get_tmp_path():
    tmp_filename = str(uuid.uuid4())
    return "/var/tmp/{}.tmp".format(tmp_filename)


class CloudInitSource(Enum):
    """Represents the cloud-init image source setting as a defined value.

    Values here represent all possible values for CLOUD_INIT_SOURCE in
    tests/integration_tests/integration_settings.py. See that file for an
    explanation of these values. If the value set there can't be parsed into
    one of these values, an exception will be raised
    """

    NONE = 1
    IN_PLACE = 2
    PROPOSED = 3
    PPA = 4
    DEB_PACKAGE = 5
    UPGRADE = 6

    def installs_new_version(self):
        return self.name not in [self.NONE.name, self.IN_PLACE.name]


class IntegrationInstance:
    def __init__(
        self,
        cloud: "IntegrationCloud",
        instance: BaseInstance,
        settings=integration_settings,
    ):
        self.cloud = cloud
        self.instance = instance
        self.settings = settings
        self._ip = ""

    def destroy(self):
        if isinstance(self.instance, GceInstance):
            self.instance.delete(wait=False)
        else:
            self.instance.delete()

    def restart(self):
        """Restart this instance (via cloud mechanism) and wait for boot.

        This wraps pycloudlib's `BaseInstance.restart`
        """
        log.info("Restarting instance and waiting for boot")
        self.instance.restart()

    def execute(self, command, *, use_sudo=True) -> Result:
        if self.instance.username == "root" and use_sudo is False:
            raise RuntimeError("Root user cannot run unprivileged")
        return self.instance.execute(command, use_sudo=use_sudo)

    def pull_file(
        self,
        remote_path: Union[str, os.PathLike],
        local_path: Union[str, os.PathLike],
    ):
        # First copy to a temporary directory because of permissions issues
        tmp_path = _get_tmp_path()
        self.instance.execute("cp {} {}".format(str(remote_path), tmp_path))
        self.instance.pull_file(tmp_path, str(local_path))

    def push_file(
        self,
        local_path: Union[str, os.PathLike],
        remote_path: Union[str, os.PathLike],
    ):
        # First push to a temporary directory because of permissions issues
        tmp_path = _get_tmp_path()
        self.instance.push_file(str(local_path), tmp_path)
        assert self.execute("mv {} {}".format(tmp_path, str(remote_path))).ok

    def read_from_file(self, remote_path) -> str:
        result = self.execute("cat {}".format(remote_path))
        if result.failed:
            # TODO: Raise here whatever pycloudlib raises when it has
            # a consistent error response
            raise IOError(
                "Failed reading remote file via cat: {}\n"
                "Return code: {}\n"
                "Stderr: {}\n"
                "Stdout: {}".format(
                    remote_path,
                    result.return_code,
                    result.stderr,
                    result.stdout,
                )
            )
        return result.stdout

    def write_to_file(self, remote_path, contents: str):
        # Writes file locally and then pushes it rather
        # than writing the file directly on the instance
        with NamedTemporaryFile("w", delete=False) as tmp_file:
            tmp_file.write(contents)

        try:
            self.push_file(tmp_file.name, remote_path)
        finally:
            os.unlink(tmp_file.name)

    def snapshot(self):
        image_id = self.cloud.snapshot(self.instance)
        log.info("Created new image: %s", image_id)
        return image_id

    def install_coverage(self):
        # Determine coverage version from integration-requirements.txt
        integration_requirements = Path(
            cloud_init_project_dir("integration-requirements.txt")
        ).read_text()
        coverage_version = ""
        for line in integration_requirements.splitlines():
            if line.startswith("coverage=="):
                coverage_version = line.split("==")[1]
                break
        else:
            raise RuntimeError(
                "Could not find coverage in integration-requirements.txt"
            )

        # Update and install coverage from pip
        # We use pip because the versions between distros are incompatible
        self._apt_update()
        self.execute("apt-get install -qy python3-pip")
        self.execute(f"pip3 install coverage=={coverage_version}")
        self.push_file(
            local_path=ASSETS_DIR / "enable_coverage.py",
            remote_path="/var/tmp/enable_coverage.py",
        )
        assert self.execute("python3 /var/tmp/enable_coverage.py").ok

    def install_profile(self):
        self.push_file(
            local_path=ASSETS_DIR / "enable_profile.py",
            remote_path="/var/tmp/enable_profile.py",
        )
        assert self.execute("python3 /var/tmp/enable_profile.py").ok

    def install_new_cloud_init(
        self,
        source: CloudInitSource,
        clean=True,
    ):
        if source == CloudInitSource.DEB_PACKAGE:
            self.install_deb()
        elif source == CloudInitSource.PPA:
            self.install_ppa()
        elif source == CloudInitSource.PROPOSED:
            self.install_proposed_image()
        elif source == CloudInitSource.UPGRADE:
            self.upgrade_cloud_init()
        else:
            raise RuntimeError(
                "Specified to install {} which isn't supported here".format(
                    source
                )
            )
        version = self.execute("cloud-init -v").split()[-1]
        log.info("Installed cloud-init version: %s", version)
        if clean:
            self.instance.clean()

    def install_proposed_image(self):
        log.info("Installing proposed image")
        assert self.execute(
            'echo deb "http://archive.ubuntu.com/ubuntu '
            '$(lsb_release -sc)-proposed main" >> '
            "/etc/apt/sources.list.d/proposed.list"
        ).ok
        self._apt_update()
        assert self.execute(
            "apt-get install -qy cloud-init -t=$(lsb_release -sc)-proposed"
        ).ok

    def install_ppa(self):
        log.info("Installing PPA")
        if self.execute("which add-apt-repository").failed:
            log.info("Installing missing software-properties-common package")
            self._apt_update()
            assert self.execute(
                "apt install -qy software-properties-common"
            ).ok
        pin_origin = self.settings.CLOUD_INIT_SOURCE[4:]  # Drop leading ppa:
        pin_origin = re.sub("[^a-z0-9-]", "-", pin_origin)
        self.write_to_file(
            "/etc/apt/preferences.d/cloud-init-integration-testing",
            f"package: cloud-init\nPin: release o=LP-PPA-{pin_origin}\n"
            "Pin-Priority: 1001\n",
        )
        assert self.execute(
            "add-apt-repository {} -y".format(self.settings.CLOUD_INIT_SOURCE)
        ).ok
        # PIN this PPA as priority for cloud-init installs regardless of ver
        assert self.execute(
            "apt-get install -qy cloud-init --allow-downgrades"
        ).ok

    @retry(tries=30, delay=1)
    def install_deb(self):
        log.info("Installing deb package")
        deb_path = integration_settings.CLOUD_INIT_SOURCE
        deb_name = os.path.basename(deb_path)
        remote_path = "/var/tmp/{}".format(deb_name)
        self.push_file(
            local_path=integration_settings.CLOUD_INIT_SOURCE,
            remote_path=remote_path,
        )
        # Update APT cache so all package data is recent to avoid inability
        # to install missing dependency errors due to stale cache.
        self.execute("apt update")
        # Use apt install instead of dpkg -i to pull in any changed pkg deps
        assert self.execute(
            f"apt install {remote_path} --yes --allow-downgrades"
        ).ok

    @retry(tries=30, delay=1)
    def upgrade_cloud_init(self):
        log.info("Upgrading cloud-init to latest version in archive")
        self._apt_update()
        assert self.execute("apt-get install -qy cloud-init").ok

    def _apt_update(self):
        """Run an apt update.

        `cloud-init single` allows us to ensure apt update is only run once
        for this instance. It could be done with an lru_cache too, but
        dogfooding is fun."""
        self.write_to_file(
            "/tmp/update-ci.yaml", "#cloud-config\npackage_update: true"
        )
        response = self.execute(
            "cloud-init single --name package_update_upgrade_install "
            "--frequency instance --file /tmp/update-ci.yaml"
        )
        if not response.ok:
            if response.stderr.startswith("usage:"):
                # https://github.com/canonical/cloud-init/pull/4559 hasn't
                # landed yet, so we need to use the old syntax
                response = self.execute(
                    "cloud-init --file /tmp/update-ci.yaml single --name "
                    "package_update_upgrade_install --frequency instance "
                )
            if response.stderr:
                raise RuntimeError(
                    f"Failed to update packages: {response.stderr}"
                )

    def ip(self) -> str:
        if self._ip:
            return self._ip
        try:
            # in some cases that ssh is not used, an address is not assigned
            if (
                isinstance(self.instance, LXDInstance)
                and self.instance.execute_via_ssh
            ):
                self._ip = self.instance.ip
        except NotImplementedError:
            self._ip = "Unknown"
        return self._ip

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.settings.KEEP_INSTANCE:
            self.destroy()
        else:
            log.info("Keeping Instance, public ip: %s", self.ip())
