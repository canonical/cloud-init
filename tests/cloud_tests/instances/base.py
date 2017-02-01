# This file is part of cloud-init. See LICENSE file for license information.

import os
import uuid


class Instance(object):
    """
    Base instance object
    """
    platform_name = None

    def __init__(self, name):
        """
        setup
        """
        self.name = name

    def execute(self, command, stdin=None, stdout=None, stderr=None, env={}):
        """
        command: the command to execute as root inside the image
        stdin, stderr, stdout: file handles
        env: environment variables

        Execute assumes functional networking and execution as root with the
        target filesystem being available at /.

        return_value: tuple containing stdout data, stderr data, exit code
        """
        raise NotImplementedError

    def read_data(self, remote_path, encode=False):
        """
        read_data from instance filesystem
        remote_path: path in instance
        decode: return as string
        return_value: data as str or bytes
        """
        raise NotImplementedError

    def write_data(self, remote_path, data):
        """
        write data to instance filesystem
        remote_path: path in instance
        data: data to write, either str or bytes
        """
        raise NotImplementedError

    def pull_file(self, remote_path, local_path):
        """
        copy file at 'remote_path', from instance to 'local_path'
        """
        with open(local_path, 'wb') as fp:
            fp.write(self.read_data(remote_path), encode=True)

    def push_file(self, local_path, remote_path):
        """
        copy file at 'local_path' to instance at 'remote_path'
        """
        with open(local_path, 'rb') as fp:
            self.write_data(remote_path, fp.read())

    def run_script(self, script):
        """
        run script in target and return stdout
        """
        script_path = os.path.join('/tmp', str(uuid.uuid1()))
        self.write_data(script_path, script)
        (out, err, exit_code) = self.execute(['/bin/bash', script_path])
        return out

    def console_log(self):
        """
        return_value: bytes of this instance’s console
        """
        raise NotImplementedError

    def reboot(self, wait=True):
        """
        reboot instance
        """
        raise NotImplementedError

    def shutdown(self, wait=True):
        """
        shutdown instance
        """
        raise NotImplementedError

    def start(self, wait=True):
        """
        start instance
        """
        raise NotImplementedError

    def destroy(self):
        """
        clean up instance
        """
        pass

    def _wait_for_cloud_init(self, wait_time):
        """
        wait until system has fully booted and cloud-init has finished
        """
        if not wait_time:
            return

        found_msg = 'found'
        cmd = ('for ((i=0;i<{wait};i++)); do [ -f "{file}" ] && '
               '{{ echo "{msg}";break; }} || sleep 1; done').format(
            file='/run/cloud-init/result.json',
            wait=wait_time, msg=found_msg)

        (out, err, exit) = self.execute(['/bin/bash', '-c', cmd])
        if out.strip() != found_msg:
            raise OSError('timeout: after {}s, cloud-init has not started'
                          .format(wait_time))

# vi: ts=4 expandtab
