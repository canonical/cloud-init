# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Foo
---
**Summary:** example module

Example to show module structure. Does not do anything.

**Internal name:** ``cc_foo``

**Module frequency:** per instance

**Supported distros:** all
"""

from cloudinit.settings import PER_INSTANCE

# Modules are expected to have the following attributes.
# 1. A required 'handle' method which takes the following params.
#    a) The name will not be this files name, but instead
#    the name specified in configuration (which is the name
#    which will be used to find this module).
#    b) A configuration object that is the result of the merging
#    of cloud configs configuration with legacy configuration
#    as well as any datasource provided configuration
#    c) A cloud object that can be used to access various
#    datasource and paths for the given distro and data provided
#    by the various datasource instance types.
#    d) A argument list that may or may not be empty to this module.
#    Typically those are from module configuration where the module
#    is defined with some extra configuration that will eventually
#    be translated from yaml into arguments to this module.
# 2. A optional 'frequency' that defines how often this module should be run.
#    Typically one of PER_INSTANCE, PER_ALWAYS, PER_ONCE. If not
#    provided PER_INSTANCE will be assumed.
#    See settings.py for these constants.
# 3. A optional 'distros' array/set/tuple that defines the known distros
#    this module will work with (if not all of them). This is used to write
#    a warning out if a module is being ran on a untested distribution for
#    informational purposes. If non existent all distros are assumed and
#    no warning occurs.

frequency = PER_INSTANCE


def handle(name, _cfg, _cloud, log, _args):
    log.debug("Hi from module %s", name)

# vi: ts=4 expandtab
