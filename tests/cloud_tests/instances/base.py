# This file is part of cloud-init. See LICENSE file for license information.

"""Base instance."""


class Instance(object):
    """Base instance object."""

    platform_name = None

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

    def execute(self, command, stdout=None, stderr=None, env=None,
                rcs=None, description=None):
        """Execute command in instance, recording output, error and exit code.

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
        raise NotImplementedError

    def read_data(self, remote_path, decode=False):
        """Read data from instance filesystem.

        @param remote_path: path in instance
        @param decode: return as string
        @return_value: data as str or bytes
        """
        raise NotImplementedError

    def write_data(self, remote_path, data):
        """Write data to instance filesystem.

        @param remote_path: path in instance
        @param data: data to write, either str or bytes
        """
        raise NotImplementedError

    def pull_file(self, remote_path, local_path):
        """Copy file at 'remote_path', from instance to 'local_path'.

        @param remote_path: path on remote instance
        @param local_path: path on local instance
        """
        with open(local_path, 'wb') as fp:
            fp.write(self.read_data(remote_path))

    def push_file(self, local_path, remote_path):
        """Copy file at 'local_path' to instance at 'remote_path'.

        @param local_path: path on local instance
        @param remote_path: path on remote instance
        """
        with open(local_path, 'rb') as fp:
            self.write_data(remote_path, fp.read())

    def run_script(self, script, rcs=None, description=None):
        """Run script in target and return stdout.

        @param script: script contents
        @param rcs: allowed return codes from script
        @param description: purpose of script
        @return_value: stdout from script
        """
        script_path = self.tmpfile()
        try:
            self.write_data(script_path, script)
            return self.execute(
                ['/bin/bash', script_path], rcs=rcs, description=description)
        finally:
            self.execute(['rm', '-f', script_path], rcs=rcs)

    def tmpfile(self):
        """Get a tmp file in the target.

        @return_value: path to new file in target
        """
        return self.execute(['mktemp'])[0].strip()

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
        pass

    def _wait_for_system(self, wait_for_cloud_init):
        """Wait until system has fully booted and cloud-init has finished.

        @param wait_time: maximum time to wait
        @return_value: None, may raise OSError if wait_time exceeded
        """
        def clean_test(test):
            """Clean formatting for system ready test testcase."""
            return ' '.join(l for l in test.strip().splitlines()
                            if not l.lstrip().startswith('#'))

        time = self.config['boot_timeout']
        tests = [self.config['system_ready_script']]
        if wait_for_cloud_init:
            tests.append(self.config['cloud_init_ready_script'])

        formatted_tests = ' && '.join(clean_test(t) for t in tests)
        cmd = ('i=0; while [ $i -lt {time} ] && i=$(($i+1)); do {test} && '
               'exit 0; sleep 1; done; exit 1').format(time=time,
                                                       test=formatted_tests)

        if self.execute(cmd, rcs=(0, 1))[-1] != 0:
            raise OSError('timeout: after {}s system not started'.format(time))


# vi: ts=4 expandtab
