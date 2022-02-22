# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
import uuid
from enum import Enum
from tempfile import NamedTemporaryFile

from pycloudlib.instance import BaseInstance
from pycloudlib.result import Result

from tests.integration_tests import integration_settings
from tests.integration_tests.util import retry

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

    def destroy(self):
        self.instance.delete()

    def restart(self):
        """Restart this instance (via cloud mechanism) and wait for boot.

        This wraps pycloudlib's `BaseInstance.restart`
        """
        log.info("Restarting instance and waiting for boot")
        self.instance.restart()

    def execute(self, command, *, use_sudo=True) -> Result:
        if self.instance.username == "root" and use_sudo is False:
            raise Exception("Root user cannot run unprivileged")
        return self.instance.execute(command, use_sudo=use_sudo)

    def pull_file(self, remote_path, local_path):
        # First copy to a temporary directory because of permissions issues
        tmp_path = _get_tmp_path()
        self.instance.execute("cp {} {}".format(str(remote_path), tmp_path))
        self.instance.pull_file(tmp_path, str(local_path))

    def push_file(self, local_path, remote_path):
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

    def install_new_cloud_init(
        self,
        source: CloudInitSource,
        take_snapshot=True,
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
            raise Exception(
                "Specified to install {} which isn't supported here".format(
                    source
                )
            )
        version = self.execute("cloud-init -v").split()[-1]
        log.info("Installed cloud-init version: %s", version)
        if clean:
            self.instance.clean()
        if take_snapshot:
            snapshot_id = self.snapshot()
            self.cloud.snapshot_id = snapshot_id

    # assert with retry because we can compete with apt already running in the
    # background and get: E: Could not get lock /var/lib/apt/lists/lock - open
    # (11: Resource temporarily unavailable)

    @retry(tries=30, delay=1)
    def install_proposed_image(self):
        log.info("Installing proposed image")
        assert self.execute(
            'echo deb "http://archive.ubuntu.com/ubuntu '
            '$(lsb_release -sc)-proposed main" >> '
            "/etc/apt/sources.list.d/proposed.list"
        ).ok
        assert self.execute("apt-get update -q").ok
        assert self.execute("apt-get install -qy cloud-init").ok

    @retry(tries=30, delay=1)
    def install_ppa(self):
        log.info("Installing PPA")
        assert self.execute(
            "add-apt-repository {} -y".format(self.settings.CLOUD_INIT_SOURCE)
        ).ok
        assert self.execute("apt-get update -q").ok
        assert self.execute("apt-get install -qy cloud-init").ok

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
        assert self.execute("dpkg -i {path}".format(path=remote_path)).ok

    @retry(tries=30, delay=1)
    def upgrade_cloud_init(self):
        log.info("Upgrading cloud-init to latest version in archive")
        assert self.execute("apt-get update -q").ok
        assert self.execute("apt-get install -qy cloud-init").ok

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.settings.KEEP_INSTANCE:
            self.destroy()
