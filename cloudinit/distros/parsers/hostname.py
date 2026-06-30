# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from io import StringIO
from typing import List, Optional, Tuple

from cloudinit.distros.parsers import chop_comment


# Parser that knows how to work with /etc/hostname format
class HostnameConf:
    def __init__(self, text: str) -> None:
        self._text = text
        self._parsed: bool = False
        self._contents: List[Tuple[str, List[str]]] = []

    def parse(self) -> None:
        if not self._parsed:
            self._contents = self._parse(self._text)
            self._parsed = True

    def __str__(self) -> str:
        self.parse()
        contents = StringIO()
        for line_type, components in self._contents:
            if line_type == "blank":
                contents.write("%s\n" % (components[0]))
            elif line_type == "all_comment":
                contents.write("%s\n" % (components[0]))
            elif line_type == "hostname":
                (hostname, tail) = components
                contents.write("%s%s\n" % (hostname, tail))
        # Ensure trailing newline
        rendered = contents.getvalue()
        if not rendered.endswith("\n"):
            rendered += "\n"
        return rendered

    @property
    def hostname(self) -> Optional[str]:
        self.parse()
        for line_type, components in self._contents:
            if line_type == "hostname":
                return components[0]
        return None

    def set_hostname(self, your_hostname: str) -> None:
        your_hostname = your_hostname.strip()
        if not your_hostname:
            return
        self.parse()
        replaced = False
        for line_type, components in self._contents:
            if line_type == "hostname":
                components[0] = str(your_hostname)
                replaced = True
        if not replaced:
            self._contents.append(("hostname", [str(your_hostname), ""]))

    def _parse(self, contents: str) -> List[Tuple[str, List[str]]]:
        entries = []
        hostnames_found = set()
        for line in contents.splitlines():
            if not len(line.strip()):
                entries.append(("blank", [line]))
                continue
            (head, tail) = chop_comment(line.strip(), "#")
            if not len(head):
                entries.append(("all_comment", [line]))
                continue
            entries.append(("hostname", [head, tail]))
            hostnames_found.add(head)
        if len(hostnames_found) > 1:
            raise IOError("Multiple hostnames (%s) found!" % (hostnames_found))
        return entries
