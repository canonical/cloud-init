import os

from mocker import MockerTestCase

from cloudinit import helpers as ch


class ResourceUsingTestCase(MockerTestCase):
    def __init__(self, methodName="runTest"):
        MockerTestCase.__init__(self, methodName)
        self.resource_path = None

    def resourceLocation(self, subname=None):
        if self.resource_path is None:
            paths = [
                os.path.join('tests', 'data'),
                os.path.join('data'),
                os.path.join(os.pardir, 'tests', 'data'),
                os.path.join(os.pardir, 'data'),
            ]
            for p in paths:
                if os.path.isdir(p):
                    self.resource_path = p
                    break
        self.assertTrue((self.resource_path and
                         os.path.isdir(self.resource_path)),
                        msg="Unable to locate test resource data path!")
        if not subname:
            return self.resource_path
        return os.path.join(self.resource_path, subname)

    def readResource(self, name):
        where = self.resourceLocation(name)
        with open(where, 'r') as fh:
            return fh.read()

    def getCloudPaths(self):
        cp = ch.Paths({
            'cloud_dir': self.makeDir(),
            'templates_dir': self.resourceLocation(),
        })
        return cp
