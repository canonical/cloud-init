# Copyright (C) 2012 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import yaml


class _CustomSafeLoader(yaml.SafeLoader):
    def construct_python_unicode(self, node):
        return self.construct_scalar(node)


_CustomSafeLoader.add_constructor(
    u'tag:yaml.org,2002:python/unicode',
    _CustomSafeLoader.construct_python_unicode)


def load(blob):
    return(yaml.load(blob, Loader=_CustomSafeLoader))

# vi: ts=4 expandtab
