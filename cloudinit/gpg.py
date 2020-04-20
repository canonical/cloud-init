# Copyright (C) 2016 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Christian Ehrhardt <christian.ehrhardt@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""gpg.py - Collection of gpg key related functions"""

from cloudinit import log as logging
from cloudinit import util

import time

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


def recv_key(key, keyserver, retries=(1, 1)):
    """Receive gpg key from the specified keyserver.

    Retries are done by default because keyservers can be unreliable.
    Additionally, there is no way to determine the difference between
    a non-existant key and a failure.  In both cases gpg (at least 2.2.4)
    exits with status 2 and stderr: "keyserver receive failed: No data"
    It is assumed that a key provided to cloud-init exists on the keyserver
    so re-trying makes better sense than failing.

    @param key: a string key fingerprint (as passed to gpg --recv-keys).
    @param keyserver: the keyserver to request keys from.
    @param retries: an iterable of sleep lengths for retries.
                    Use None to indicate no retries."""
    LOG.debug("Importing key '%s' from keyserver '%s'", key, keyserver)
    cmd = ["gpg", "--keyserver=%s" % keyserver, "--recv-keys", key]
    if retries is None:
        retries = []
    trynum = 0
    error = None
    sleeps = iter(retries)
    while True:
        trynum += 1
        try:
            util.subp(cmd, capture=True)
            LOG.debug("Imported key '%s' from keyserver '%s' on try %d",
                      key, keyserver, trynum)
            return
        except util.ProcessExecutionError as e:
            error = e
        try:
            naplen = next(sleeps)
            LOG.debug(
                "Import failed with exit code %d, will try again in %ss",
                error.exit_code, naplen)
            time.sleep(naplen)
        except StopIteration:
            raise ValueError(
                ("Failed to import key '%s' from keyserver '%s' "
                 "after %d tries: %s") % (key, keyserver, trynum, error))


def delete_key(key):
    """Delete the specified key from the local gpg ring"""
    try:
        util.subp(["gpg", "--batch", "--yes", "--delete-keys", key],
                  capture=True)
    except util.ProcessExecutionError as error:
        LOG.warning('Failed delete key "%s": %s', key, error)


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
