# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
import uuid
from tempfile import NamedTemporaryFile

from pycloudlib.instance import BaseInstance
from pycloudlib.result import Result

from tests.integration_tests import integration_settings

try:
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from tests.integration_tests.clouds import IntegrationCloud
except ImportError:
    pass


log = logging.getLogger('integration_testing')


def _get_tmp_path():
    tmp_filename = str(uuid.uuid4())
    return '/var/tmp/{}.tmp'.format(tmp_filename)


class IntegrationInstance:
    use_sudo = True

    def __init__(self, cloud: 'IntegrationCloud', instance: BaseInstance,
                 settings=integration_settings):
        self.cloud = cloud
        self.instance = instance
        self.settings = settings

    def destroy(self):
        self.instance.delete()

    def execute(self, command, *, use_sudo=None) -> Result:
        if self.instance.username == 'root' and use_sudo is False:
            raise Exception('Root user cannot run unprivileged')
        if use_sudo is None:
            use_sudo = self.use_sudo
        return self.instance.execute(command, use_sudo=use_sudo)

    def pull_file(self, remote_path, local_path):
        # First copy to a temporary directory because of permissions issues
        tmp_path = _get_tmp_path()
        self.instance.execute('cp {} {}'.format(remote_path, tmp_path))
        self.instance.pull_file(tmp_path, local_path)

    def push_file(self, local_path, remote_path):
        # First push to a temporary directory because of permissions issues
        tmp_path = _get_tmp_path()
        self.instance.push_file(local_path, tmp_path)
        self.execute('mv {} {}'.format(tmp_path, remote_path))

    def read_from_file(self, remote_path) -> str:
        result = self.execute('cat {}'.format(remote_path))
        if result.failed:
            # TODO: Raise here whatever pycloudlib raises when it has
            # a consistent error response
            raise IOError(
                'Failed reading remote file via cat: {}\n'
                'Return code: {}\n'
                'Stderr: {}\n'
                'Stdout: {}'.format(
                    remote_path, result.return_code,
                    result.stderr, result.stdout)
            )
        return result.stdout

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
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.settings.KEEP_INSTANCE:
            self.destroy()


class IntegrationEc2Instance(IntegrationInstance):
    pass


class IntegrationGceInstance(IntegrationInstance):
    pass


class IntegrationAzureInstance(IntegrationInstance):
    pass


class IntegrationOciInstance(IntegrationInstance):
    pass


class IntegrationLxdInstance(IntegrationInstance):
    use_sudo = False
