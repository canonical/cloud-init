# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import types

import six


if six.PY3:
    _NAME_TYPES = (
        types.ModuleType,
        types.FunctionType,
        types.LambdaType,
        type,
    )
else:
    _NAME_TYPES = (
        types.TypeType,
        types.ModuleType,
        types.FunctionType,
        types.LambdaType,
        types.ClassType,
    )


def obj_name(obj):
    if isinstance(obj, _NAME_TYPES):
        return six.text_type(obj.__name__)
    else:
        if not hasattr(obj, '__class__'):
            return repr(obj)
        else:
            return obj_name(obj.__class__)

# vi: ts=4 expandtab
