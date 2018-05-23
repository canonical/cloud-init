# This file is part of cloud-init. See LICENSE file for license information.

"""Base instance."""
import time

import paramiko
from paramiko.ssh_exception import (
    BadHostKeyException, AuthenticationException, SSHException)

from ..util import TargetBase
from tests.cloud_tests import LOG, util


class Instance(TargetBase):
    """Base instance object."""

    platform_name = None
    _ssh_client = None

    def __init__(self, platform, name, properties, config, features):
        """Set up instance.

        @param platform: platform object
        @param name: hostname of instance
        @param properties: image properties
        @param config: image config
        @param features: supported feature flags
        """
        self.platform = platform
        self.name = name
        self.properties = properties
        self.config = config
        self.features = features
        self._tmp_count = 0

        self.ssh_ip = None
        self.ssh_port = None
        self.ssh_key_file = None
        self.ssh_username = 'ubuntu'

    def console_log(self):
        """Instance console.

        @return_value: bytes of this instance’s console
        """
        raise NotImplementedError

    def reboot(self, wait=True):
        """Reboot instance."""
        raise NotImplementedError

    def shutdown(self, wait=True):
        """Shutdown instance."""
        raise NotImplementedError

    def start(self, wait=True, wait_for_cloud_init=False):
        """Start instance."""
        raise NotImplementedError

    def destroy(self):
        """Clean up instance."""
        self._ssh_close()

    def _ssh(self, command, stdin=None):
        """Run a command via SSH."""
        client = self._ssh_connect()

        cmd = util.shell_pack(command)
        fp_in, fp_out, fp_err = client.exec_command(cmd)
        channel = fp_in.channel

        if stdin is not None:
            fp_in.write(stdin)
            fp_in.close()

        channel.shutdown_write()
        rc = channel.recv_exit_status()

        return (fp_out.read(), fp_err.read(), rc)

    def _ssh_close(self):
        if self._ssh_client:
            try:
                self._ssh_client.close()
            except SSHException:
                LOG.warning('Failed to close SSH connection.')
            self._ssh_client = None

    def _ssh_connect(self):
        """Connect via SSH.

        Attempt to SSH to the client on the specific IP and port. If it
        fails in some manner, then retry 2 more times for a total of 3
        attempts; sleeping a few seconds between attempts.
        """
        if self._ssh_client:
            return self._ssh_client

        if not self.ssh_ip or not self.ssh_port:
            raise ValueError

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = paramiko.RSAKey.from_private_key_file(self.ssh_key_file)

        retries = 3
        while retries:
            try:
                client.connect(username=self.ssh_username,
                               hostname=self.ssh_ip, port=self.ssh_port,
                               pkey=private_key)
                self._ssh_client = client
                return client
            except (ConnectionRefusedError, AuthenticationException,
                    BadHostKeyException, ConnectionResetError, SSHException,
                    OSError):
                retries -= 1
                LOG.debug('Retrying ssh connection on connect failure')
                time.sleep(3)

        ssh_cmd = 'Failed ssh connection to %s@%s:%s after 3 retries' % (
            self.ssh_username, self.ssh_ip, self.ssh_port
        )
        raise util.InTargetExecuteError(b'', b'', 1, ssh_cmd, 'ssh')

    def _wait_for_system(self, wait_for_cloud_init):
        """Wait until system has fully booted and cloud-init has finished.

        @param wait_time: maximum time to wait
        @return_value: None, may raise OSError if wait_time exceeded
        """
        def clean_test(test):
            """Clean formatting for system ready test testcase."""
            return ' '.join(l for l in test.strip().splitlines()
                            if not l.lstrip().startswith('#'))

        boot_timeout = self.config['boot_timeout']
        tests = [self.config['system_ready_script']]
        if wait_for_cloud_init:
            tests.append(self.config['cloud_init_ready_script'])

        formatted_tests = ' && '.join(clean_test(t) for t in tests)
        cmd = ('i=0; while [ $i -lt {time} ] && i=$(($i+1)); do {test} && '
               'exit 0; sleep 1; done; exit 1').format(time=boot_timeout,
                                                       test=formatted_tests)

        end_time = time.time() + boot_timeout
        while True:
            try:
                return_code = self.execute(
                    cmd, rcs=(0, 1), description='wait for instance start'
                )[-1]
                if return_code == 0:
                    break
            except util.InTargetExecuteError:
                LOG.warning("failed to connect via SSH")

            if time.time() < end_time:
                time.sleep(3)
            else:
                raise util.PlatformError('ssh', 'after %ss instance is not '
                                         'reachable' % boot_timeout)

# vi: ts=4 expandtab
