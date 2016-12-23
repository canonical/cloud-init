# This file is part of cloud-init. See LICENSE file for license information.


class Image(object):
    """
    Base class for images
    """
    platform_name = None

    def __init__(self, name, config, platform):
        """
        setup
        """
        self.name = name
        self.config = config
        self.platform = platform

    def __str__(self):
        """
        a brief description of the image
        """
        return '-'.join((self.properties['os'], self.properties['release']))

    @property
    def properties(self):
        """
        {} containing: 'arch', 'os', 'version', 'release'
        """
        raise NotImplementedError

    # FIXME: instead of having execute and push_file and other instance methods
    #        here which pass through to a hidden instance, it might be better
    #        to expose an instance that the image can be modified through
    def execute(self, command, stdin=None, stdout=None, stderr=None, env={}):
        """
        execute command in image, modifying image
        """
        raise NotImplementedError

    def push_file(self, local_path, remote_path):
        """
        copy file at 'local_path' to instance at 'remote_path', modifying image
        """
        raise NotImplementedError

    def run_script(self, script):
        """
        run script in image, modifying image
        return_value: script output
        """
        raise NotImplementedError

    def snapshot(self):
        """
        create snapshot of image, block until done
        """
        raise NotImplementedError

    def destroy(self):
        """
        clean up data associated with image
        """
        pass

# vi: ts=4 expandtab
