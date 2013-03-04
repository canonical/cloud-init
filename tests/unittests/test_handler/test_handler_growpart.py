from mocker import MockerTestCase

from cloudinit import cloud
from cloudinit import helpers
from cloudinit import util

from cloudinit.config import cc_growpart

import logging
import os
import mocker

# growpart:
#   mode: auto  # off, on, auto, 'growpart', 'parted'
#   devices: ['root']

HELP_PARTED_NO_RESIZE = """
Usage: parted [OPTION]... [DEVICE [COMMAND [PARAMETERS]...]...]
Apply COMMANDs with PARAMETERS to DEVICE.  If no COMMAND(s) are given, run in
interactive mode.

OPTIONs:
<SNIP>

COMMANDs:
<SNIP>
  quit                                     exit program
  rescue START END                         rescue a lost partition near START
        and END
  resize NUMBER START END                  resize partition NUMBER and its file
        system
  rm NUMBER                                delete partition NUMBER
<SNIP>
Report bugs to bug-parted@gnu.org
"""

HELP_PARTED_RESIZE = """
Usage: parted [OPTION]... [DEVICE [COMMAND [PARAMETERS]...]...]
Apply COMMANDs with PARAMETERS to DEVICE.  If no COMMAND(s) are given, run in
interactive mode.

OPTIONs:
<SNIP>

COMMANDs:
<SNIP>
  quit                                     exit program
  rescue START END                         rescue a lost partition near START
        and END
  resize NUMBER START END                  resize partition NUMBER and its file
        system
  resizepart NUMBER END                    resize partition NUMBER
  rm NUMBER                                delete partition NUMBER
<SNIP>
Report bugs to bug-parted@gnu.org
"""

HELP_GROWPART_RESIZE = """
growpart disk partition
   rewrite partition table so that partition takes up all the space it can
   options:
    -h | --help       print Usage and exit
<SNIP>
    -u | --update  R  update the the kernel partition table info after growing
                      this requires kernel support and 'partx --update'
                      R is one of:
                       - 'auto'  : [default] update partition if possible
<SNIP>
   Example:
    - growpart /dev/sda 1
      Resize partition 1 on /dev/sda
"""

HELP_GROWPART_NO_RESIZE = """
growpart disk partition
   rewrite partition table so that partition takes up all the space it can
   options:
    -h | --help       print Usage and exit
<SNIP>
   Example:
    - growpart /dev/sda 1
      Resize partition 1 on /dev/sda
"""

class TestDisabled(MockerTestCase):
    def setUp(self):
        super(TestDisabled, self).setUp()
        self.name = "growpart"
        self.cloud_init = None
        self.log = logging.getLogger("TestDisabled")
        self.args = []

        self.handle = cc_growpart.handle

    def test_mode_off(self):
        #Test that nothing is done if mode is off.
        config = {'growpart': {'mode': 'off'}}
        self.mocker.replay()

        self.handle(self.name, config, self.cloud_init, self.log, self.args)

    def test_no_config(self):
        #Test that nothing is done if no 'growpart' config
        config = { }
        self.mocker.replay()

        self.handle(self.name, config, self.cloud_init, self.log, self.args)


class TestConfig(MockerTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.name = "growpart"
        self.paths = None
        self.cloud = cloud.Cloud(None, self.paths, None, None, None)
        self.log = logging.getLogger("TestConfig")
        self.args = []
        os.environ = {}

        self.cloud_init = None
        self.handle = cc_growpart.handle

        # Order must be correct
        self.mocker.order()

    def test_no_resizers_auto_is_fine(self):
        subp = self.mocker.replace(util.subp, passthrough=False)
        subp(['parted', '--help'], env={'LANG': 'C'})
        self.mocker.result((HELP_PARTED_NO_RESIZE,""))
        subp(['growpart', '--help'], env={'LANG': 'C'})
        self.mocker.result((HELP_GROWPART_NO_RESIZE,""))
        self.mocker.replay()

        config = {'growpart': {'mode': 'auto'}}
        self.handle(self.name, config, self.cloud_init, self.log, self.args)

    def test_no_resizers_mode_growpart_is_exception(self):
        subp = self.mocker.replace(util.subp, passthrough=False)
        subp(['growpart', '--help'], env={'LANG': 'C'})
        self.mocker.result((HELP_GROWPART_NO_RESIZE,""))
        self.mocker.replay()

        config = {'growpart': {'mode': "growpart"}}
        self.assertRaises(ValueError, self.handle, self.name, config,
                          self.cloud_init, self.log, self.args)

    def test_mode_auto_prefers_parted(self):
        subp = self.mocker.replace(util.subp, passthrough=False)
        subp(['parted', '--help'], env={'LANG': 'C'})
        self.mocker.result((HELP_PARTED_RESIZE,""))
        self.mocker.replay()

        ret = cc_growpart.resizer_factory(mode="auto")
        self.assertTrue(isinstance(ret, cc_growpart.ResizeParted))

# vi: ts=4 expandtab
