# This file is part of cloud-init. See LICENSE file for license information.

"""Base LXD instance."""

from . import base

import os
import shutil
from tempfile import mkdtemp


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
        self.tmpd = mkdtemp(prefix="%s-%s" % (type(self).__name__, name))
        self._setup_console_log()

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

        if stdin is not None:
            # pylxd does not support input to execute.
            # https://github.com/lxc/pylxd/issues/244
            #
            # The solution here is write a tmp file in the container
            # and then execute a shell that sets it standard in to
            # be from that file, removes it, and calls the comand.
            tmpf = self.tmpfile()
            self.write_data(tmpf, stdin)
            ncmd = 'exec <"{tmpf}"; rm -f "{tmpf}"; exec "$@"'
            command = (['sh', '-c', ncmd.format(tmpf=tmpf), 'stdinhack'] +
                       list(command))

        # ensure instance is running and execute the command
        self.start()
        # execute returns a ContainerExecuteResult, named tuple
        # (exit_code, stdout, stderr)
        res = self.pylxd_container.execute(command, environment=env)

        # get out, exit and err from pylxd return
        if not hasattr(res, 'exit_code'):
            # pylxd 2.1.3 and earlier only return out and err, no exit
            raise RuntimeError(
                "No 'exit_code' in pylxd.container.execute return.\n"
                "pylxd > 2.2 is required.")

        return res.stdout, res.stderr, res.exit_code

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
