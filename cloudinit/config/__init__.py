# Copyright (C) 2008-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Chuck Short <chuck.short@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.settings import (PER_INSTANCE, FREQUENCIES)

from cloudinit import log as logging

LOG = logging.getLogger(__name__)

# This prefix is used to make it less
# of a chance that when importing
# we will not find something else with the same
# name in the lookup path...
MOD_PREFIX = "cc_"


def form_module_name(name):
    canon_name = name.replace("-", "_")
    if canon_name.lower().endswith(".py"):
        canon_name = canon_name[0:(len(canon_name) - 3)]
    canon_name = canon_name.strip()
    if not canon_name:
        return None
    if not canon_name.startswith(MOD_PREFIX):
        canon_name = '%s%s' % (MOD_PREFIX, canon_name)
    return canon_name


def fixup_module(mod, def_freq=PER_INSTANCE):
    if not hasattr(mod, 'frequency'):
        setattr(mod, 'frequency', def_freq)
    else:
        freq = mod.frequency
        if freq and freq not in FREQUENCIES:
            LOG.warn("Module %s has an unknown frequency %s", mod, freq)
    if not hasattr(mod, 'distros'):
        setattr(mod, 'distros', [])
    if not hasattr(mod, 'osfamilies'):
        setattr(mod, 'osfamilies', [])
    return mod

# vi: ts=4 expandtab
