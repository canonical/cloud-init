# Copyright (C) 2016 Canonical Ltd.
#
# Author: Ryan Harper <ryan.harper@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Snappy
------
**Summary:** snap_config modules allows configuration of snapd.

This module uses the same ``snappy`` namespace for configuration but
acts only only a subset of the configuration.

If ``assertions`` is set and the user has included a list of assertions
then cloud-init will collect the assertions into a single assertion file
and invoke ``snap ack <path to file with assertions>`` which will attempt
to load the provided assertions into the snapd assertion database.

If ``email`` is set, this value is used to create an authorized user for
contacting and installing snaps from the Ubuntu Store.  This is done by
calling ``snap create-user`` command.

If ``known`` is set to True, then it is expected the user also included
an assertion of type ``system-user``.  When ``snap create-user`` is called
cloud-init will append '--known' flag which instructs snapd to look for
a system-user assertion with the details.  If ``known`` is not set, then
``snap create-user`` will contact the Ubuntu SSO for validating and importing
a system-user for the instance.

.. note::
    If the system is already managed, then cloud-init will not attempt to
    create a system-user.

**Internal name:** ``cc_snap_config``

**Module frequency:** per instance

**Supported distros:** any with 'snapd' available

**Config keys**::

    #cloud-config
    snappy:
        assertions:
        - |
        <assertion 1>
        - |
        <assertion 2>
        email: user@user.org
        known: true

"""

from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import util

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE
SNAPPY_CMD = "snap"
ASSERTIONS_FILE = "/var/lib/cloud/instance/snapd.assertions"


"""
snappy:
  assertions:
  - |
  <snap assertion 1>
  - |
  <snap assertion 2>
  email: foo@foo.io
  known: true
"""


def add_assertions(assertions=None):
    """Import list of assertions.

    Import assertions by concatenating each assertion into a
    string separated by a '\n'.  Write this string to a instance file and
    then invoke `snap ack /path/to/file` and check for errors.
    If snap exits 0, then all assertions are imported.
    """
    if not assertions:
        assertions = []

    if not isinstance(assertions, list):
        raise ValueError('assertion parameter was not a list: %s', assertions)

    snap_cmd = [SNAPPY_CMD, 'ack']
    combined = "\n".join(assertions)
    if len(combined) == 0:
        raise ValueError("Assertion list is empty")

    for asrt in assertions:
        LOG.debug('Acking: %s', asrt.split('\n')[0:2])

    util.write_file(ASSERTIONS_FILE, combined.encode('utf-8'))
    util.subp(snap_cmd + [ASSERTIONS_FILE], capture=True)


def add_snap_user(cfg=None):
    """Add a snap system-user if provided with email under snappy config.

      - Check that system is not already managed.
      - Check that if using a system-user assertion, that it's
        imported into snapd.

    Returns a dictionary to be passed to Distro.create_user
    """

    if not cfg:
        cfg = {}

    if not isinstance(cfg, dict):
        raise ValueError('configuration parameter was not a dict: %s', cfg)

    snapuser = cfg.get('email', None)
    if not snapuser:
        return

    usercfg = {
        'snapuser': snapuser,
        'known': cfg.get('known', False),
    }

    # query if we're already registered
    out, _ = util.subp([SNAPPY_CMD, 'managed'], capture=True)
    if out.strip() == "true":
        LOG.warning('This device is already managed. '
                    'Skipping system-user creation')
        return

    if usercfg.get('known'):
        # Check that we imported a system-user assertion
        out, _ = util.subp([SNAPPY_CMD, 'known', 'system-user'],
                           capture=True)
        if len(out) == 0:
            LOG.error('Missing "system-user" assertion. '
                      'Check "snappy" user-data assertions.')
            return

    return usercfg


def handle(name, cfg, cloud, log, args):
    cfgin = cfg.get('snappy')
    if not cfgin:
        LOG.debug('No snappy config provided, skipping')
        return

    if not(util.system_is_snappy()):
        LOG.debug("%s: system not snappy", name)
        return

    assertions = cfgin.get('assertions', [])
    if len(assertions) > 0:
        LOG.debug('Importing user-provided snap assertions')
        add_assertions(assertions)

    # Create a snap user if requested.
    # Snap systems contact the store with a user's email
    # and extract information needed to create a local user.
    # A user may provide a 'system-user' assertion which includes
    # the required information. Using such an assertion to create
    # a local user requires specifying 'known: true' in the supplied
    # user-data.
    usercfg = add_snap_user(cfg=cfgin)
    if usercfg:
        cloud.distro.create_user(usercfg.get('snapuser'), **usercfg)

# vi: ts=4 expandtab
