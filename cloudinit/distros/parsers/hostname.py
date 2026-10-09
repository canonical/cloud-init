# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from io import StringIO
from typing import Any, List, Optional, Set, Tuple

from cloudinit.distros.parsers import chop_comment


# Parser that knows how to work with /etc/hostname format
class HostnameConf:
    def __init__(self, text: str) -> None:
        self._text = text
        self._contents: Optional[List[Tuple[str, List[Any]]]] = None

    def parse(self) -> None:
        if self._contents is None:
            self._contents = self._parse(self._text)

    def __str__(self) -> str:
        self.parse()
        if self._contents is None:
            return ""
        contents = StringIO()
        for line_type, components in self._contents:
            if line_type == "blank":
                contents.write("%s\n" % (components[0]))
            elif line_type == "all_comment":
                contents.write("%s\n" % (components[0]))
            elif line_type == "hostname":
                hostname, tail = components
                contents.write("%s%s\n" % (hostname, tail))
        # Ensure trailing newline
        output = contents.getvalue()
        if not output.endswith("\n"):
            output += "\n"
        return output

    @property
    def hostname(self) -> Optional[str]:
        self.parse()
        if self._contents is None:
            return None
        for line_type, components in self._contents:
            if line_type == "hostname":
                return components[0]
        return None

    def set_hostname(self, your_hostname: str) -> None:
        your_hostname = your_hostname.strip()
        if not your_hostname:
            return
        self.parse()
        if self._contents is None:
            return
        replaced = False
        for line_type, components in self._contents:
            if line_type == "hostname":
                components[0] = str(your_hostname)
                replaced = True
        if not replaced:
            self._contents.append(("hostname", [str(your_hostname), ""]))

    def _parse(self, contents: str) -> List[Tuple[str, List[Any]]]:
        entries: List[Tuple[str, List[Any]]] = []
        hostnames_found: Set[str] = set()
        for line in contents.splitlines():
            if not len(line.strip()):
                entries.append(("blank", [line]))
                continue
            head, tail = chop_comment(line.strip(), "#")
            if not len(head):
                entries.append(("all_comment", [line]))
                continue
            entries.append(("hostname", [head, tail]))
            hostnames_found.add(head)
        if len(hostnames_found) > 1:
            raise IOError("Multiple hostnames (%s) found!" % (hostnames_found))
        return entries
