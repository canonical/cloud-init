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


class NoCloudKVMInstance(base.Instance):
    """NoCloud KVM backed instance."""

    platform_name = "nocloud-kvm"

    def __init__(self, platform, name, properties, config, features,
                 user_data, meta_data):
        """Set up instance.

        @param platform: platform object
        @param name: image path
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
        super(NoCloudKVMInstance, self).destroy()

    def execute(self, command, stdout=None, stderr=None, env=None,
                rcs=None, description=None):
        """Execute command in instance.

        Assumes functional networking and execution as root with the
        target filesystem being available at /.

        @param command: the command to execute as root inside the image
            if command is a string, then it will be executed as:
            ['sh', '-c', command]
        @param stdout, stderr: file handles to write output and error to
        @param env: environment variables
        @param rcs: allowed return codes from command
        @param description: purpose of command
        @return_value: tuple containing stdout data, stderr data, exit code
        """
        if env is None:
            env = {}

        if isinstance(command, str):
            command = ['sh', '-c', command]

        if self.pid:
            return self.ssh(command)
        else:
            return self.mount_image_callback(command) + (0,)

    def mount_image_callback(self, cmd):
        """Run mount-image-callback."""
        out, err = c_util.subp(['sudo', 'mount-image-callback',
                                '--system-mounts', '--system-resolvconf',
                                self.name, '--', 'chroot',
                                '_MOUNTPOINT_'] + cmd)

        return out, err

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

    def push_file(self, local_path, remote_path):
        """Copy file at 'local_path' to instance at 'remote_path'.

        If we have a pid then SSH is up, otherwise, use
        mount-image-callback.

        @param local_path: path on local instance
        @param remote_path: path on remote instance
        """
        if self.pid:
            super(NoCloudKVMInstance, self).push_file()
        else:
            local_file = open(local_path)
            p = subprocess.Popen(['sudo', 'mount-image-callback',
                                  '--system-mounts', '--system-resolvconf',
                                  self.name, '--', 'chroot', '_MOUNTPOINT_',
                                  '/bin/sh', '-c', 'cat - > %s' % remote_path],
                                 stdin=local_file,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            p.wait()

    def sftp_put(self, path, data):
        """SFTP put a file."""
        client = self._ssh_connect()
        sftp = client.open_sftp()

        with sftp.open(path, 'w') as f:
            f.write(data)

        client.close()

    def ssh(self, command):
        """Run a command via SSH."""
        client = self._ssh_connect()

        try:
            _, out, err = client.exec_command(util.shell_pack(command))
        except paramiko.SSHException:
            raise util.InTargetExecuteError('', '', -1, command, self.name)

        exit = out.channel.recv_exit_status()
        out = ''.join(out.readlines())
        err = ''.join(err.readlines())
        client.close()

        return out, err, exit

    def _ssh_connect(self, hostname='localhost', username='ubuntu',
                     banner_timeout=120, retry_attempts=30):
        """Connect via SSH."""
        private_key = paramiko.RSAKey.from_private_key_file(self.ssh_key_file)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        while retry_attempts:
            try:
                client.connect(hostname=hostname, username=username,
                               port=self.ssh_port, pkey=private_key,
                               banner_timeout=banner_timeout)
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
        self.ssh_port = self.get_free_port()

        subprocess.Popen(['./tools/xkvm',
                          '--disk', '%s,cache=unsafe' % self.name,
                          '--disk', '%s,cache=unsafe' % seed,
                          '--netdev',
                          'user,hostfwd=tcp::%s-:22' % self.ssh_port,
                          '--', '-pidfile', self.pid_file, '-vnc', 'none',
                          '-m', '2G', '-smp', '2'],
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

    def write_data(self, remote_path, data):
        """Write data to instance filesystem.

        @param remote_path: path in instance
        @param data: data to write, either str or bytes
        """
        self.sftp_put(remote_path, data)

# vi: ts=4 expandtab
