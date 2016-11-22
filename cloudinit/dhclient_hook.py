# This file is part of cloud-init. See LICENSE file for license information.

import os

from cloudinit import atomic_helper
from cloudinit import log as logging
from cloudinit import stages

LOG = logging.getLogger(__name__)


class LogDhclient(object):

    def __init__(self, cli_args):
        self.hooks_dir = self._get_hooks_dir()
        self.net_interface = cli_args.net_interface
        self.net_action = cli_args.net_action
        self.hook_file = os.path.join(self.hooks_dir,
                                      self.net_interface + ".json")

    @staticmethod
    def _get_hooks_dir():
        i = stages.Init()
        return os.path.join(i.paths.get_runpath(), 'dhclient.hooks')

    def check_hooks_dir(self):
        if not os.path.exists(self.hooks_dir):
            os.makedirs(self.hooks_dir)
        else:
            # If the action is down and the json file exists, we need to
            # delete the file
            if self.net_action is 'down' and os.path.exists(self.hook_file):
                os.remove(self.hook_file)

    @staticmethod
    def get_vals(info):
        new_info = {}
        for k, v in info.items():
            if k.startswith("DHCP4_") or k.startswith("new_"):
                key = (k.replace('DHCP4_', '').replace('new_', '')).lower()
                new_info[key] = v
        return new_info

    def record(self):
        envs = os.environ
        if self.hook_file is None:
            return
        atomic_helper.write_json(self.hook_file, self.get_vals(envs))
        LOG.debug("Wrote dhclient options in %s", self.hook_file)

# vi: ts=4 expandtab
