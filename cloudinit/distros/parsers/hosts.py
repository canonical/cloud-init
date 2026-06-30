# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from io import StringIO
from typing import Any, List, Tuple

from cloudinit.distros.parsers import chop_comment


# See: man hosts
# or https://linux.die.net/man/5/hosts
# or https://www.freebsd.org/doc/en_US.ISO8859-1/books/handbook/configtuning-configfiles.html # noqa
class HostsConf:
    def __init__(self, text: str) -> None:
        self._text = text
        self._contents: List[Tuple[str, List[Any]]] = []

    def parse(self) -> None:
        if not self._contents:
            self._contents = self._parse(self._text)

    def get_entry(self, ip: str) -> List[List[str]]:
        self.parse()
        options: List[List[str]] = []
        for line_type, components in self._contents:
            if line_type == "option":
                pieces, _tail = components
                if len(pieces) and pieces[0] == ip:
                    options.append(pieces[1:])
        return options

    def del_entries(self, ip: str) -> None:
        self.parse()
        n_entries: List[Tuple[str, List[Any]]] = []
        for line_type, components in self._contents:
            if line_type != "option":
                n_entries.append((line_type, components))
                continue
            else:
                pieces, _tail = components
                if len(pieces) and pieces[0] == ip:
                    pass
                elif len(pieces):
                    n_entries.append((line_type, list(components)))
        self._contents = n_entries

    def add_entry(
        self, ip: str, canonical_hostname: str, *aliases: str
    ) -> None:
        self.parse()
        self._contents.append(
            ("option", [[ip, canonical_hostname] + list(aliases), ""])
        )

    def _parse(self, contents: str) -> List[Tuple[str, List[Any]]]:
        entries: List[Tuple[str, List[Any]]] = []
        for line in contents.splitlines():
            if not len(line.strip()):
                entries.append(("blank", [line]))
                continue
            head, tail = chop_comment(line.strip(), "#")
            if not len(head):
                entries.append(("all_comment", [line]))
                continue
            entries.append(("option", [head.split(None), tail]))
        return entries

    def __str__(self) -> str:
        self.parse()
        contents = StringIO()
        for line_type, components in self._contents:
            if line_type == "blank":
                contents.write("%s\n" % components[0])
            elif line_type == "all_comment":
                contents.write("%s\n" % components[0])
            elif line_type == "option":
                raw_pieces, tail = components
                str_pieces = [str(p) for p in raw_pieces]
                joined = "\t".join(str_pieces)
                contents.write(f"{joined}{tail}\n")
        return contents.getvalue()
