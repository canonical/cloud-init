# Copyright (C) 2017 Red Hat, Inc.
#
# Author: Ryan McCabe <rmccabe@redhat.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import configparser

# This module is used to set additional NetworkManager configuration
# in /etc/NetworkManager/conf.d
#


class NetworkManagerConf:
    def __init__(self, contents):
        self._parser = configparser.RawConfigParser()
        self._parser.optionxform = str  # type: ignore[method-assign,assignment]
        if contents:
            if isinstance(contents, (list, tuple)):
                contents = "\n".join(contents)
            if isinstance(contents, bytes):
                contents = contents.decode("utf-8")
            self._parser.read_string(contents)

    @property
    def sections(self):
        return self._parser.sections()

    def __bool__(self):
        return bool(self._parser.sections())

    def set_section_keypair(self, section_name, key, value):
        if section_name not in self._parser.sections():
            self._parser.add_section(section_name)
        self._parser.set(section_name, key, value)

    def write(self):
        lines = []
        for section in self._parser.sections():
            lines.append("[%s]" % section)
            for key, value in self._parser.items(section):
                lines.append("%s = %s" % (key, value))
        return lines
