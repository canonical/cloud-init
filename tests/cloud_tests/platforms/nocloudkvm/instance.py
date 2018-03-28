# This file is part of cloud-init. See LICENSE file for license information.

"""Base NoCloud KVM instance."""

import copy
import os
import socket
import subprocess
import time
import uuid

from ..instances import Instance
from cloudinit.atomic_helper import write_json
from cloudinit import util as c_util
from tests.cloud_tests import LOG, util

# This domain contains reverse lookups for hostnames that are used.
# The primary reason is so sudo will return quickly when it attempts
# to look up the hostname.  i9n is just short for 'integration'.
# see also bug 1730744 for why we had to do this.
CI_DOMAIN = "i9n.cloud-init.io"


class NoCloudKVMInstance(Instance):
    """NoCloud KVM backed instance."""

    platform_name = "nocloud-kvm"

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
        super(NoCloudKVMInstance, self).__init__(
            platform, name, properties, config, features
        )

        self.user_data = user_data
        if meta_data:
            meta_data = copy.deepcopy(meta_data)
        else:
            meta_data = {}

        if 'instance-id' in meta_data:
            iid = meta_data['instance-id']
        else:
            iid = str(uuid.uuid1())
            meta_data['instance-id'] = iid

        self.instance_id = iid
        self.ssh_key_file = os.path.join(
            platform.config['data_dir'], platform.config['private_key'])
        self.ssh_pubkey_file = os.path.join(
            platform.config['data_dir'], platform.config['public_key'])

        self.ssh_pubkey = None
        if self.ssh_pubkey_file:
            with open(self.ssh_pubkey_file, "r") as fp:
                self.ssh_pubkey = fp.read().rstrip('\n')

            if not meta_data.get('public-keys'):
                meta_data['public-keys'] = []
            meta_data['public-keys'].append(self.ssh_pubkey)

        self.ssh_ip = '127.0.0.1'
        self.ssh_port = None
        self.pid = None
        self.pid_file = None
        self.console_file = None
        self.disk = image_path
        self.meta_data = meta_data

    def shutdown(self, wait=True):
        """Shutdown instance."""

        if self.pid:
            # This relies on _execute which uses sudo over ssh.  The ssh
            # connection would get killed before sudo exited, so ignore errors.
            cmd = ['shutdown', 'now']
            try:
                self._execute(cmd)
            except util.InTargetExecuteError:
                pass
            self._ssh_close()

            if wait:
                LOG.debug("Executed shutdown. waiting on pid %s to end",
                          self.pid)
                time_for_shutdown = 120
                give_up_at = time.time() + time_for_shutdown
                pid_file_path = '/proc/%s' % self.pid
                msg = ("pid %s did not exit in %s seconds after shutdown." %
                       (self.pid, time_for_shutdown))
                while True:
                    if not os.path.exists(pid_file_path):
                        break
                    if time.time() > give_up_at:
                        raise util.PlatformError("shutdown", msg)
                self.pid = None

    def destroy(self):
        """Clean up instance."""
        if self.pid:
            try:
                c_util.subp(['kill', '-9', self.pid])
            except c_util.ProcessExecutionError:
                pass

        if self.pid_file:
            os.remove(self.pid_file)

        self.pid = None
        self._ssh_close()

        super(NoCloudKVMInstance, self).destroy()

    def _execute(self, command, stdin=None, env=None):
        env_args = []
        if env:
            env_args = ['env'] + ["%s=%s" for k, v in env.items()]

        return self._ssh(['sudo'] + env_args + list(command), stdin=stdin)

    def generate_seed(self, tmpdir):
        """Generate nocloud seed from user-data"""
        seed_file = os.path.join(tmpdir, '%s_seed.img' % self.name)
        user_data_file = os.path.join(tmpdir, '%s_user_data' % self.name)
        meta_data_file = os.path.join(tmpdir, '%s_meta_data' % self.name)

        with open(user_data_file, "w") as ud_file:
            ud_file.write(self.user_data)

        # meta-data can be yaml, but more easily pretty printed with json
        write_json(meta_data_file, self.meta_data)
        c_util.subp(['cloud-localds', seed_file, user_data_file,
                     meta_data_file])

        return seed_file

    def get_free_port(self):
        """Get a free port assigned by the kernel."""
        s = socket.socket()
        s.bind(('', 0))
        num = s.getsockname()[1]
        s.close()
        return num

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
