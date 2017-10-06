# This file is part of cloud-init. See LICENSE file for license information.

"""Base LXD instance."""

from tests.cloud_tests.instances import base
from tests.cloud_tests import util


class LXDInstance(base.Instance):
    """LXD container backed instance."""

    platform_name = "lxd"

    def __init__(self, platform, name, properties, config, features,
                 pylxd_container):
        """Set up instance.

        @param platform: platform object
        @param name: hostname of instance
        @param properties: image properties
        @param config: image config
        @param features: supported feature flags
        """
        self._pylxd_container = pylxd_container
        super(LXDInstance, self).__init__(
            platform, name, properties, config, features)

    @property
    def pylxd_container(self):
        """Property function."""
        self._pylxd_container.sync()
        return self._pylxd_container

    def execute(self, command, stdout=None, stderr=None, env=None,
                rcs=None, description=None):
        """Execute command in instance, recording output, error and exit code.

        Assumes functional networking and execution as root with the
        target filesystem being available at /.

        @param command: the command to execute as root inside the image
            if command is a string, then it will be executed as:
            ['sh', '-c', command]
        @param stdout: file handler to write output
        @param stderr: file handler to write error
        @param env: environment variables
        @param rcs: allowed return codes from command
        @param description: purpose of command
        @return_value: tuple containing stdout data, stderr data, exit code
        """
        if env is None:
            env = {}

        if isinstance(command, str):
            command = ['sh', '-c', command]

        # ensure instance is running and execute the command
        self.start()
        res = self.pylxd_container.execute(command, environment=env)

        # get out, exit and err from pylxd return
        if hasattr(res, 'exit_code'):
            # pylxd 2.2 returns ContainerExecuteResult, named tuple of
            # (exit_code, out, err)
            (exit, out, err) = res
        else:
            # pylxd 2.1.3 and earlier only return out and err, no exit
            # LOG.warning('using pylxd version < 2.2')
            (out, err) = res
            exit = 0

        # write data to file descriptors if needed
        if stdout:
            stdout.write(out)
        if stderr:
            stderr.write(err)

        # if the command exited with a code not allowed in rcs, then fail
        if exit not in (rcs if rcs else (0,)):
            error_desc = ('Failed command to: {}'.format(description)
                          if description else None)
            raise util.InTargetExecuteError(
                out, err, exit, command, self.name, error_desc)

        return (out, err, exit)

    def read_data(self, remote_path, decode=False):
        """Read data from instance filesystem.

        @param remote_path: path in instance
        @param decode: return as string
        @return_value: data as str or bytes
        """
        data = self.pylxd_container.files.get(remote_path)
        return data.decode() if decode and isinstance(data, bytes) else data

    def write_data(self, remote_path, data):
        """Write data to instance filesystem.

        @param remote_path: path in instance
        @param data: data to write, either str or bytes
        """
        self.pylxd_container.files.put(remote_path, data)

    def console_log(self):
        """Console log.

        @return_value: bytes of this instance’s console
        """
        raise NotImplementedError

    def reboot(self, wait=True):
        """Reboot instance."""
        self.shutdown(wait=wait)
        self.start(wait=wait)

    def shutdown(self, wait=True):
        """Shutdown instance."""
        if self.pylxd_container.status != 'Stopped':
            self.pylxd_container.stop(wait=wait)

    def start(self, wait=True, wait_for_cloud_init=False):
        """Start instance."""
        if self.pylxd_container.status != 'Running':
            self.pylxd_container.start(wait=wait)
            if wait:
                self._wait_for_system(wait_for_cloud_init)

    def freeze(self):
        """Freeze instance."""
        if self.pylxd_container.status != 'Frozen':
            self.pylxd_container.freeze(wait=True)

    def unfreeze(self):
        """Unfreeze instance."""
        if self.pylxd_container.status == 'Frozen':
            self.pylxd_container.unfreeze(wait=True)

    def destroy(self):
        """Clean up instance."""
        self.unfreeze()
        self.shutdown()
        self.pylxd_container.delete(wait=True)
        if self.platform.container_exists(self.name):
            raise OSError('container {} was not properly removed'
                          .format(self.name))
        super(LXDInstance, self).destroy()

# vi: ts=4 expandtab
