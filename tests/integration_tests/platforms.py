from io import StringIO

from pycloudlib import OCI, LXD
from pycloudlib.cloud import BaseCloud
from pycloudlib.instance import BaseInstance

from tests.integration_tests import integration_settings

try:
    from typing import Callable, Optional
except ImportError:
    pass

ALL_PLATFORMS = [
    'lxd_container',
    'oracle'
]

current_image = None


def set_current_image(image):
    global current_image
    current_image = image


class IntegrationClient:
    client = None  # type: Optional[BaseCloud]
    instance = None  # type: Optional[BaseInstance]
    datasource = None  # type: Optional[str]

    def __init__(self, user_data=None, instance_type=None, wait=True,
                 settings=integration_settings, launch_kwargs=None):
        self.user_data = user_data
        self.instance_type = settings.INSTANCE_TYPE if \
            instance_type is None else instance_type
        self.wait = wait
        self.settings = settings
        self.launch_kwargs = launch_kwargs if launch_kwargs else {}

    def _get_image(self):
        if current_image:
            return current_image
        image_id = self.settings.OS_IMAGE
        try:
            image_id = self.client.released_image(self.settings.OS_IMAGE)
        except (ValueError, IndexError):
            pass
        return image_id

    def launch(self):
        if self.settings.EXISTING_INSTANCE_ID:
            print('Not launching instance due to EXISTING_INSTANCE_ID. '
                  'Instance id: {}'.format(self.settings.EXISTING_INSTANCE_ID))
            self.instance = self.client.get_instance(
                self.settings.EXISTING_INSTANCE_ID
            )
            return
        image_id = self._get_image()
        launch_args = {
            'image_id': image_id,
            'user_data': self.user_data,
            'wait': self.wait,
        }
        if self.instance_type:
            launch_args['instance_type'] = self.instance_type
        launch_args.update(self.launch_kwargs)
        self.instance = self.client.launch(**launch_args)
        print('Launched instance: {}'.format(self.instance))

    def destroy(self):
        self.instance.delete()

    def exec(self, command):
        return self.instance.execute(command)

    def get_file(self, remote_file, local_file=None):
        if not local_file:
            local_file = StringIO()
        self.instance.pull_file(remote_file, local_file)
        return local_file

    def put_file(self, local_path, remote_path):
        self.instance.push_file(local_path, remote_path)

    def snapshot(self):
        return self.client.snapshot(self.instance, clean=True, wait=True)

    def generate_proposed_image(self, sudo=False):
        print('Generating proposed image')
        remote_script = (
            '{sudo} echo deb "http://archive.ubuntu.com/ubuntu '
            '$(lsb_release -sc)-proposed main" | '
            '{sudo} tee /etc/apt/sources.list.d/proposed.list\n'
            '{sudo} apt-get update -q\n'
            '{sudo} apt-get install -qy cloud-init'
        ).format(sudo='sudo' if sudo else '')
        self.exec(remote_script)
        version = self.exec('cloud-init -v').split()[-1]
        print('Installed cloud-init version: {}'.format(version))
        self.instance.clean()
        image_id = self.snapshot()
        print('Created proposed image: {}'.format(image_id))
        set_current_image(image_id)

    def __enter__(self):
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.settings.KEEP_INSTANCE:
            self.destroy()


class OracleClient(IntegrationClient):
    datasource = 'oracle'

    def __init__(self, user_data=None, instance_type=None, wait=True,
                 settings=integration_settings, launch_kwargs=None):
        super().__init__(
            user_data,
            instance_type,
            wait,
            settings,
            launch_kwargs
        )
        self.client = OCI(
            tag='OCI Integration Test',
            compartment_id=self.settings.ORACLE_COMPARTMENT_ID
        )

    def generate_proposed_image(self, sudo=True):
        super().generate_proposed_image(sudo)


class LxdContainerClient(IntegrationClient):
    datasource = 'lxd_container'

    def __init__(self, user_data=None, instance_type=None, wait=True,
                 settings=integration_settings, launch_kwargs=None):
        super().__init__(
            user_data,
            instance_type,
            wait,
            settings,
            launch_kwargs
        )
        self.client = LXD(
            tag='LXD Integration Test'
        )


client_name_to_class = {
    'oracle': OracleClient,
    'lxd_container': LxdContainerClient
}

try:
    dynamic_client = client_name_to_class[
        integration_settings.PLATFORM
    ]  # type: Callable[..., IntegrationClient]
except KeyError:
    raise ValueError(
        "{} is an invalid PLATFORM specified in settings. "
        "Must be one of {}".format(
            integration_settings.PLATFORM, ALL_PLATFORMS
        )
    )
