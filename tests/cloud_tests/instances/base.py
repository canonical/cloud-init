# This file is part of cloud-init. See LICENSE file for license information.

"""Base instance."""

from ..util import TargetBase


class Instance(TargetBase):
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
        self._tmp_count = 0

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
