# This file is part of cloud-init. See LICENSE file for license information.
from abc import ABC
import logging
import os
from tempfile import NamedTemporaryFile

from pycloudlib.instance import BaseInstance

import cloudinit
from cloudinit.subp import subp
from tests.integration_tests import integration_settings

try:
    from typing import Optional
except ImportError:
    pass


log = logging.getLogger('integration_testing')


class CloudInstance(ABC):
    datasource = None  # type: Optional[str]
    use_sudo = True

    def __init__(self, cloud, user_data=None,
                 settings=integration_settings, launch_kwargs=None):
        self.cloud = cloud
        self.user_data = user_data
        self.settings = settings
        self.launch_kwargs = launch_kwargs if launch_kwargs else {}

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

    def launch(self):
        if self.settings.EXISTING_INSTANCE_ID:
            log.info(
                'Not launching instance due to EXISTING_INSTANCE_ID. '
                'Instance id: %s', self.settings.EXISTING_INSTANCE_ID)
            self.instance = self.cloud.get_instance(
                self.settings.EXISTING_INSTANCE_ID
            )
            return
        launch_kwargs = {
            'image_id': self.cloud.image_id,
            'user_data': self.user_data,
            'wait': False,
        }
        launch_kwargs.update(self.launch_kwargs)
        self.instance = self.cloud.cloud_instance.launch(**launch_kwargs)
        self.instance.wait(raise_on_cloudinit_failure=False)
        log.info('Launched instance: %s', self.instance)

    def destroy(self):
        self.instance.delete()

    def execute(self, command):
        return self.instance.execute(command)

    def pull_file(self, remote_file, local_file):
        self.instance.pull_file(remote_file, local_file)

    def push_file(self, local_path, remote_path):
        self.instance.push_file(local_path, remote_path)

    def read_from_file(self, remote_path) -> str:
        tmp_file = NamedTemporaryFile('r')
        self.pull_file(remote_path, tmp_file.name)
        with tmp_file as f:
            contents = f.read()
        return contents

    def write_to_file(self, remote_path, contents: str):
        # Writes file locally and then pushes it rather
        # than writing the file directly on the instance
        with NamedTemporaryFile('w', delete=False) as tmp_file:
            tmp_file.write(contents)

        try:
            self.push_file(tmp_file.name, remote_path)
        finally:
            os.unlink(tmp_file.name)

    def snapshot(self):
        return self.cloud.snapshot(self.instance)

    def _install_new_cloud_init(self, remote_script):
        self.execute(remote_script)
        version = self.execute('cloud-init -v').split()[-1]
        log.info('Installed cloud-init version: %s', version)
        self.instance.clean()
        image_id = self.snapshot()
        log.info('Created new image: %s', image_id)
        self.cloud.image_id = image_id

    def install_proposed_image(self):
        log.info('Installing proposed image')
        remote_script = (
            '{sudo} echo deb "http://archive.ubuntu.com/ubuntu '
            '$(lsb_release -sc)-proposed main" | '
            '{sudo} tee /etc/apt/sources.list.d/proposed.list\n'
            '{sudo} apt-get update -q\n'
            '{sudo} apt-get install -qy cloud-init'
        ).format(sudo='sudo' if self.use_sudo else '')
        self._install_new_cloud_init(remote_script)

    def install_ppa(self, repo):
        log.info('Installing PPA')
        remote_script = (
            '{sudo} add-apt-repository {repo} -y && '
            '{sudo} apt-get update -q && '
            '{sudo} apt-get install -qy cloud-init'
        ).format(sudo='sudo' if self.use_sudo else '', repo=repo)
        self._install_new_cloud_init(remote_script)

    def install_deb(self):
        log.info('Installing deb package')
        deb_path = integration_settings.CLOUD_INIT_SOURCE
        deb_name = os.path.basename(deb_path)
        remote_path = '/var/tmp/{}'.format(deb_name)
        self.push_file(
            local_path=integration_settings.CLOUD_INIT_SOURCE,
            remote_path=remote_path)
        remote_script = '{sudo} dpkg -i {path}'.format(
            sudo='sudo' if self.use_sudo else '', path=remote_path)
        self._install_new_cloud_init(remote_script)

    def __enter__(self):
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.settings.KEEP_INSTANCE:
            self.destroy()


class Ec2Instance(CloudInstance):
    datasource = 'ec2'


class GceInstance(CloudInstance):
    datasource = 'gce'


class AzureInstance(CloudInstance):
    datasource = 'azure'


class OciInstance(CloudInstance):
    datasource = 'oci'


class LxdContainerInstance(CloudInstance):
    datasource = 'lxd_container'
    use_sudo = False

    def _mount_source(self):
        command = (
            'lxc config device add {name} host-cloud-init disk '
            'source={cloudinit_path} '
            'path=/usr/lib/python3/dist-packages/cloudinit'
        ).format(
            name=self.instance.name, cloudinit_path=cloudinit.__path__[0])
        subp(command.split())

    def launch(self):
        super().launch()
        if self.settings.CLOUD_INIT_SOURCE == 'IN_PLACE':
            self._mount_source()
