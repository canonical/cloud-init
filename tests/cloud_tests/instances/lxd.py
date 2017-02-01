# This file is part of cloud-init. See LICENSE file for license information.

from tests.cloud_tests.instances import base


class LXDInstance(base.Instance):
    """
    LXD container backed instance
    """
    platform_name = "lxd"

    def __init__(self, name, platform, pylxd_container):
        """
        setup
        """
        self.platform = platform
        self._pylxd_container = pylxd_container
        super(LXDInstance, self).__init__(name)

    @property
    def pylxd_container(self):
        self._pylxd_container.sync()
        return self._pylxd_container

    def execute(self, command, stdin=None, stdout=None, stderr=None, env={}):
        """
        command: the command to execute as root inside the image
        stdin, stderr, stdout: file handles
        env: environment variables

        Execute assumes functional networking and execution as root with the
        target filesystem being available at /.

        return_value: tuple containing stdout data, stderr data, exit code
        """
        # TODO: the pylxd api handler for container.execute needs to be
        #       extended to properly pass in stdin
        # TODO: the pylxd api handler for container.execute needs to be
        #       extended to get the return code, for now just use 0
        self.start()
        if stdin:
            raise NotImplementedError
        res = self.pylxd_container.execute(command, environment=env)
        for (f, data) in (i for i in zip((stdout, stderr), res) if i[0]):
            f.write(data)
        return res + (0,)

    def read_data(self, remote_path, decode=False):
        """
        read data from instance filesystem
        remote_path: path in instance
        decode: return as string
        return_value: data as str or bytes
        """
        data = self.pylxd_container.files.get(remote_path)
        return data.decode() if decode and isinstance(data, bytes) else data

    def write_data(self, remote_path, data):
        """
        write data to instance filesystem
        remote_path: path in instance
        data: data to write, either str or bytes
        """
        self.pylxd_container.files.put(remote_path, data)

    def console_log(self):
        """
        return_value: bytes of this instance’s console
        """
        raise NotImplementedError

    def reboot(self, wait=True):
        """
        reboot instance
        """
        self.shutdown(wait=wait)
        self.start(wait=wait)

    def shutdown(self, wait=True):
        """
        shutdown instance
        """
        if self.pylxd_container.status != 'Stopped':
            self.pylxd_container.stop(wait=wait)

    def start(self, wait=True, wait_time=None):
        """
        start instance
        """
        if self.pylxd_container.status != 'Running':
            self.pylxd_container.start(wait=wait)
            if wait and isinstance(wait_time, int):
                self._wait_for_cloud_init(wait_time)

    def freeze(self):
        """
        freeze instance
        """
        if self.pylxd_container.status != 'Frozen':
            self.pylxd_container.freeze(wait=True)

    def unfreeze(self):
        """
        unfreeze instance
        """
        if self.pylxd_container.status == 'Frozen':
            self.pylxd_container.unfreeze(wait=True)

    def destroy(self):
        """
        clean up instance
        """
        self.unfreeze()
        self.shutdown()
        self.pylxd_container.delete(wait=True)
        if self.platform.container_exists(self.name):
            raise OSError('container {} was not properly removed'
                          .format(self.name))
        super(LXDInstance, self).destroy()

# vi: ts=4 expandtab
