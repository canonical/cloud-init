# This file is part of cloud-init. See LICENSE file for license information.

"""Base LXD instance."""

import os
import shutil
from tempfile import mkdtemp

from cloudinit.util import load_yaml, subp, ProcessExecutionError, which
from tests.cloud_tests import LOG
from tests.cloud_tests.util import PlatformError

from ..instances import Instance

from pylxd import exceptions as pylxd_exc


class LXDInstance(Instance):
    """LXD container backed instance."""

    platform_name = "lxd"
    _console_log_method = None
    _console_log_file = None

    def __init__(self, platform, name, properties, config, features,
                 pylxd_container):
        """Set up instance.

        @param platform: platform object
        @param name: hostname of instance
        @param properties: image properties
        @param config: image config
        @param features: supported feature flags
        """
        if not pylxd_container:
            raise ValueError("Invalid value pylxd_container: %s" %
                             pylxd_container)
        self._pylxd_container = pylxd_container
        super(LXDInstance, self).__init__(
            platform, name, properties, config, features)
        self.tmpd = mkdtemp(prefix="%s-%s" % (type(self).__name__, name))
        self.name = name
        self._setup_console_log()

    @property
    def pylxd_container(self):
        """Property function."""
        if self._pylxd_container is None:
            raise RuntimeError(
                "%s: Attempted use of pylxd_container after deletion." % self)
        self._pylxd_container.sync()
        return self._pylxd_container

    def __str__(self):
        return (
            '%s(name=%s) status=%s' %
            (self.__class__.__name__, self.name,
             ("deleted" if self._pylxd_container is None else
              self.pylxd_container.status)))

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

    @property
    def console_log_method(self):
        if self._console_log_method is not None:
            return self._console_log_method

        client = which('lxc')
        if not client:
            raise PlatformError("No 'lxc' client.")

        elif _has_proper_console_support():
            self._console_log_method = 'show-log'
        elif client.startswith("/snap"):
            self._console_log_method = 'logfile-snap'
        else:
            self._console_log_method = 'logfile-tmp'

        LOG.debug("Set console log method to %s", self._console_log_method)
        return self._console_log_method

    def _setup_console_log(self):
        method = self.console_log_method
        if not method.startswith("logfile-"):
            return

        if method == "logfile-snap":
            log_dir = "/var/snap/lxd/common/consoles"
            if not os.path.exists(log_dir):
                raise PlatformError(
                    "Unable to log with snap lxc.  Please run:\n"
                    "  sudo mkdir --mode=1777 -p %s" % log_dir)
        elif method == "logfile-tmp":
            log_dir = "/tmp"
        else:
            raise PlatformError(
                "Unexpected value for console method: %s" % method)

        # doing this ensures we can read it. Otherwise it ends up root:root.
        log_file = os.path.join(log_dir, self.name)
        with open(log_file, "w") as fp:
            fp.write("# %s\n" % self.name)

        cfg = "lxc.console.logfile=%s" % log_file
        orig = self._pylxd_container.config.get('raw.lxc', "")
        if orig:
            orig += "\n"
        self._pylxd_container.config['raw.lxc'] = orig + cfg
        self._pylxd_container.save()
        self._console_log_file = log_file

    def console_log(self):
        """Console log.

        @return_value: bytes of this instance's console
        """

        if self._console_log_file:
            if not os.path.exists(self._console_log_file):
                raise NotImplementedError(
                    "Console log '%s' does not exist. If this is a remote "
                    "lxc, then this is really NotImplementedError.  If it is "
                    "A local lxc, then this is a RuntimeError."
                    "https://github.com/lxc/lxd/issues/1129")
            with open(self._console_log_file, "rb") as fp:
                return fp.read()

        try:
            return subp(['lxc', 'console', '--show-log', self.name],
                        decode=False)[0]
        except ProcessExecutionError as e:
            raise PlatformError(
                "console log",
                "Console log failed [%d]: stdout=%s stderr=%s" % (
                    e.exit_code, e.stdout, e.stderr))

    def reboot(self, wait=True):
        """Reboot instance."""
        self.shutdown(wait=wait)
        self.start(wait=wait)

    def shutdown(self, wait=True, retry=1):
        """Shutdown instance."""
        if self.pylxd_container.status == 'Stopped':
            return

        try:
            LOG.debug("%s: shutting down (wait=%s)", self, wait)
            self.pylxd_container.stop(wait=wait)
        except (pylxd_exc.LXDAPIException, pylxd_exc.NotFound) as e:
            # An exception happens here sometimes (LP: #1783198)
            # LOG it, and try again.
            LOG.warning(
                ("%s: shutdown(retry=%d) caught %s in shutdown "
                 "(response=%s): %s"),
                self, retry, e.__class__.__name__, e.response, e)
            if isinstance(e, pylxd_exc.NotFound):
                LOG.debug("container_exists(%s) == %s",
                          self.name, self.platform.container_exists(self.name))
            if retry == 0:
                raise e
            return self.shutdown(wait=wait, retry=retry - 1)

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
        LOG.debug("%s: deleting container.", self)
        self.unfreeze()
        self.shutdown()
        self.pylxd_container.delete(wait=True)
        self._pylxd_container = None

        if self.platform.container_exists(self.name):
            raise OSError('%s: container was not properly removed' % self)
        if self._console_log_file and os.path.exists(self._console_log_file):
            os.unlink(self._console_log_file)
        shutil.rmtree(self.tmpd)
        super(LXDInstance, self).destroy()


def _has_proper_console_support():
    stdout, _ = subp(['lxc', 'info'])
    info = load_yaml(stdout)
    reason = None
    if 'console' not in info.get('api_extensions', []):
        reason = "LXD server does not support console api extension"
    else:
        dver = str(info.get('environment', {}).get('driver_version', ""))
        if dver.startswith("2.") or dver.startswith("1."):
            reason = "LXD Driver version not 3.x+ (%s)" % dver
        else:
            try:
                stdout = subp(['lxc', 'console', '--help'], decode=False)[0]
                if not (b'console' in stdout and b'log' in stdout):
                    reason = "no '--log' in lxc console --help"
            except ProcessExecutionError:
                reason = "no 'console' command in lxc client"

    if reason:
        LOG.debug("no console-support: %s", reason)
        return False
    else:
        LOG.debug("console-support looks good")
        return True


# vi: ts=4 expandtab
