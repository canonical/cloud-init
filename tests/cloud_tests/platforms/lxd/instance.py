# This file is part of cloud-init. See LICENSE file for license information.

"""Base LXD instance."""

import os
import shutil
from tempfile import mkdtemp

from cloudinit.util import subp, ProcessExecutionError

from ..instances import Instance


class LXDInstance(Instance):
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
        self.tmpd = mkdtemp(prefix="%s-%s" % (type(self).__name__, name))
        self._setup_console_log()
        self.name = name

    @property
    def pylxd_container(self):
        """Property function."""
        self._pylxd_container.sync()
        return self._pylxd_container

    def _setup_console_log(self):
        logf = os.path.join(self.tmpd, "console.log")

        # doing this ensures we can read it. Otherwise it ends up root:root.
        with open(logf, "w") as fp:
            fp.write("# %s\n" % self.name)

        cfg = "lxc.console.logfile=%s" % logf
        orig = self._pylxd_container.config.get('raw.lxc', "")
        if orig:
            orig += "\n"
        self._pylxd_container.config['raw.lxc'] = orig + cfg
        self._pylxd_container.save()
        self._console_log_file = logf

    def _execute(self, command, stdin=None, env=None):
        if env is None:
            env = {}

        env_args = []
        if env:
            env_args = ['env'] + ["%s=%s" for k, v in env.items()]

        # ensure instance is running and execute the command
        self.start()

        # Use cmdline client due to https://github.com/lxc/pylxd/issues/268
        exit_code = 0
        try:
            stdout, stderr = subp(
                ['lxc', 'exec', self.name, '--'] + env_args + list(command),
                data=stdin, decode=False)
        except ProcessExecutionError as e:
            exit_code = e.exit_code
            stdout = e.stdout
            stderr = e.stderr

        return stdout, stderr, exit_code

    def read_data(self, remote_path, decode=False):
        """Read data from instance filesystem.

        @param remote_path: path in instance
        @param decode: decode data before returning.
        @return_value: content of remote_path as bytes if 'decode' is False,
                       and as string if 'decode' is True.
        """
        data = self.pylxd_container.files.get(remote_path)
        return data.decode() if decode else data

    def write_data(self, remote_path, data):
        """Write data to instance filesystem.

        @param remote_path: path in instance
        @param data: data to write in bytes
        """
        self.pylxd_container.files.put(remote_path, data)

    def console_log(self):
        """Console log.

        @return_value: bytes of this instance’s console
        """
        if not os.path.exists(self._console_log_file):
            raise NotImplementedError(
                "Console log '%s' does not exist. If this is a remote "
                "lxc, then this is really NotImplementedError.  If it is "
                "A local lxc, then this is a RuntimeError."
                "https://github.com/lxc/lxd/issues/1129")
        with open(self._console_log_file, "rb") as fp:
            return fp.read()

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
        shutil.rmtree(self.tmpd)
        super(LXDInstance, self).destroy()

# vi: ts=4 expandtab
