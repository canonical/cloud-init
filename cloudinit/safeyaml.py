# Copyright (C) 2012 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import yaml

YAMLError = yaml.YAMLError


class _CustomSafeLoader(yaml.SafeLoader):
    def construct_python_unicode(self, node):
        return self.construct_scalar(node)


_CustomSafeLoader.add_constructor(
    u'tag:yaml.org,2002:python/unicode',
    _CustomSafeLoader.construct_python_unicode)


class NoAliasSafeDumper(yaml.dumper.SafeDumper):
    """A class which avoids constructing anchors/aliases on yaml dump"""

    def ignore_aliases(self, data):
        return True


def load(blob):
    return(yaml.load(blob, Loader=_CustomSafeLoader))


def dumps(obj, explicit_start=True, explicit_end=True, noalias=False):
    """Return data in nicely formatted yaml."""

    return yaml.dump(obj,
                     line_break="\n",
                     indent=4,
                     explicit_start=explicit_start,
                     explicit_end=explicit_end,
                     default_flow_style=False,
                     Dumper=(NoAliasSafeDumper
                             if noalias else yaml.dumper.Dumper))

# vi: ts=4 expandtab
