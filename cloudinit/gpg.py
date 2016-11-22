# Copyright (C) 2016 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Christian Ehrhardt <christian.ehrhardt@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""gpg.py - Collection of gpg key related functions"""

from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)


def export_armour(key):
    """Export gpg key, armoured key gets returned"""
    try:
        (armour, _) = util.subp(["gpg", "--export", "--armour", key],
                                capture=True)
    except util.ProcessExecutionError as error:
        # debug, since it happens for any key not on the system initially
        LOG.debug('Failed to export armoured key "%s": %s', key, error)
        armour = None
    return armour


def recv_key(key, keyserver):
    """Receive gpg key from the specified keyserver"""
    LOG.debug('Receive gpg key "%s"', key)
    try:
        util.subp(["gpg", "--keyserver", keyserver, "--recv", key],
                  capture=True)
    except util.ProcessExecutionError as error:
        raise ValueError(('Failed to import key "%s" '
                          'from server "%s" - error %s') %
                         (key, keyserver, error))


def delete_key(key):
    """Delete the specified key from the local gpg ring"""
    try:
        util.subp(["gpg", "--batch", "--yes", "--delete-keys", key],
                  capture=True)
    except util.ProcessExecutionError as error:
        LOG.warn('Failed delete key "%s": %s', key, error)


def getkeybyid(keyid, keyserver='keyserver.ubuntu.com'):
    """get gpg keyid from keyserver"""
    armour = export_armour(keyid)
    if not armour:
        try:
            recv_key(keyid, keyserver=keyserver)
            armour = export_armour(keyid)
        except ValueError:
            LOG.exception('Failed to obtain gpg key %s', keyid)
            raise
        finally:
            # delete just imported key to leave environment as it was before
            delete_key(keyid)

    return armour

# vi: ts=4 expandtab
