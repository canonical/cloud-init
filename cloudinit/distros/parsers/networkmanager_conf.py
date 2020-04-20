# Copyright (C) 2017 Red Hat, Inc.
#
# Author: Ryan McCabe <rmccabe@redhat.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import configobj

# This module is used to set additional NetworkManager configuration
# in /etc/NetworkManager/conf.d
#


class NetworkManagerConf(configobj.ConfigObj):
    def __init__(self, contents):
        configobj.ConfigObj.__init__(self, contents,
                                     interpolation=False,
                                     write_empty_values=False)

    def set_section_keypair(self, section_name, key, value):
        if section_name not in self.sections:
            self.main[section_name] = {}
        self.main[section_name] = {key: value}
