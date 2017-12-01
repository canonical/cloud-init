# This file is part of cloud-init. See LICENSE file for license information.

"""Base NoCloud KVM instance."""

import os
import paramiko
import socket
import subprocess
import time

from cloudinit import util as c_util
from tests.cloud_tests.instances import base
from tests.cloud_tests import util

# This domain contains reverse lookups for hostnames that are used.
# The primary reason is so sudo will return quickly when it attempts
# to look up the hostname.  i9n is just short for 'integration'.
# see also bug 1730744 for why we had to do this.
CI_DOMAIN = "i9n.cloud-init.io"


class NoCloudKVMInstance(base.Instance):
    """NoCloud KVM backed instance."""

    platform_name = "nocloud-kvm"
    _ssh_client = None

    def __init__(self, platform, name, image_path, properties, config,
                 features, user_data, meta_data):
        """Set up instance.

        @param platform: platform object
        @param name: image path
        @param image_path: path to disk image to boot.
        @param properties: dictionary of properties
        @param config: dictionary of configuration values
        @param features: dictionary of supported feature flags
        """
        self.user_data = user_data
        self.meta_data = meta_data
        self.ssh_key_file = os.path.join(platform.config['data_dir'],
                                         platform.config['private_key'])
        self.ssh_port = None
        self.pid = None
        self.pid_file = None
        self.console_file = None
        self.disk = image_path

        super(NoCloudKVMInstance, self).__init__(
            platform, name, properties, config, features)

    def destroy(self):
        """Clean up instance."""
        if self.pid:
            try:
                c_util.subp(['kill', '-9', self.pid])
            except util.ProcessExectuionError:
                pass

        if self.pid_file:
            os.remove(self.pid_file)

        self.pid = None
        if self._ssh_client:
            self._ssh_client.close()
            self._ssh_client = None

        super(NoCloudKVMInstance, self).destroy()

    def _execute(self, command, stdin=None, env=None):
        env_args = []
        if env:
            env_args = ['env'] + ["%s=%s" for k, v in env.items()]

        return self.ssh(['sudo'] + env_args + list(command), stdin=stdin)

    def generate_seed(self, tmpdir):
        """Generate nocloud seed from user-data"""
        seed_file = os.path.join(tmpdir, '%s_seed.img' % self.name)
        user_data_file = os.path.join(tmpdir, '%s_user_data' % self.name)

        with open(user_data_file, "w") as ud_file:
            ud_file.write(self.user_data)

        c_util.subp(['cloud-localds', seed_file, user_data_file])

        return seed_file

    def get_free_port(self):
        """Get a free port assigned by the kernel."""
        s = socket.socket()
        s.bind(('', 0))
        num = s.getsockname()[1]
        s.close()
        return num

    def ssh(self, command, stdin=None):
        """Run a command via SSH."""
        client = self._ssh_connect()

        cmd = util.shell_pack(command)
        try:
            fp_in, fp_out, fp_err = client.exec_command(cmd)
            channel = fp_in.channel
            if stdin is not None:
                fp_in.write(stdin)
                fp_in.close()

            channel.shutdown_write()
            rc = channel.recv_exit_status()
            return (fp_out.read(), fp_err.read(), rc)
        except paramiko.SSHException as e:
            raise util.InTargetExecuteError(
                b'', b'', -1, command, self.name, reason=e)

    def _ssh_connect(self, hostname='localhost', username='ubuntu',
                     banner_timeout=120, retry_attempts=30):
        """Connect via SSH."""
        if self._ssh_client:
            return self._ssh_client

        private_key = paramiko.RSAKey.from_private_key_file(self.ssh_key_file)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        while retry_attempts:
            try:
                client.connect(hostname=hostname, username=username,
                               port=self.ssh_port, pkey=private_key,
                               banner_timeout=banner_timeout)
                self._ssh_client = client
                return client
            except (paramiko.SSHException, TypeError):
                time.sleep(1)
                retry_attempts = retry_attempts - 1

        error_desc = 'Failed command to: %s@%s:%s' % (username, hostname,
                                                      self.ssh_port)
        raise util.InTargetExecuteError('', '', -1, 'ssh connect',
                                        self.name, error_desc)

    def start(self, wait=True, wait_for_cloud_init=False):
        """Start instance."""
        tmpdir = self.platform.config['data_dir']
        seed = self.generate_seed(tmpdir)
        self.pid_file = os.path.join(tmpdir, '%s.pid' % self.name)
        self.console_file = os.path.join(tmpdir, '%s-console.log' % self.name)
        self.ssh_port = self.get_free_port()

        cmd = ['./tools/xkvm',
               '--disk', '%s,cache=unsafe' % self.disk,
               '--disk', '%s,cache=unsafe' % seed,
               '--netdev', ','.join(['user',
                                     'hostfwd=tcp::%s-:22' % self.ssh_port,
                                     'dnssearch=%s' % CI_DOMAIN]),
               '--', '-pidfile', self.pid_file, '-vnc', 'none',
               '-m', '2G', '-smp', '2', '-nographic',
               '-serial', 'file:' + self.console_file]
        subprocess.Popen(cmd,
                         close_fds=True,
                         stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)

        while not os.path.exists(self.pid_file):
            time.sleep(1)

        with open(self.pid_file, 'r') as pid_f:
            self.pid = pid_f.readlines()[0].strip()

        if wait:
            self._wait_for_system(wait_for_cloud_init)

    def console_log(self):
        if not self.console_file:
            return b''
        with open(self.console_file, "rb") as fp:
            return fp.read()

# vi: ts=4 expandtab
