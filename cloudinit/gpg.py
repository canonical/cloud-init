"""gpg.py - Collection of gpg key related functions"""
# vi: ts=4 expandtab
#
#    Copyright (C) 2016 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#    Author: Christian Ehrhardt <christian.ehrhardt@canonical.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from cloudinit import util
from cloudinit import log as logging

LOG = logging.getLogger(__name__)


def gpg_export_armour(key):
    """Export gpg key, armoured key gets returned"""
    try:
        (armour, _) = util.subp(["gpg", "--export", "--armour", key],
                                capture=True)
    except util.ProcessExecutionError as error:
        # debug, since it happens for any key not on the system initially
        LOG.debug('Failed to export armoured key "%s": %s', key, error)
        armour = None
    return armour


def gpg_recv_key(key, keyserver):
    """Receive gpg key from the specified keyserver"""
    LOG.debug('Receive gpg key "%s"', key)
    try:
        util.subp(["gpg", "--keyserver", keyserver, "--recv", key],
                  capture=True)
    except util.ProcessExecutionError as error:
        raise ValueError(('Failed to import key "%s" '
                          'from server "%s" - error %s') %
                         (key, keyserver, error))


def gpg_delete_key(key):
    """Delete the specified key from the local gpg ring"""
    try:
        util.subp(["gpg", "--batch", "--yes", "--delete-keys", key],
                  capture=True)
    except util.ProcessExecutionError as error:
        LOG.warn('Failed delete key "%s": %s', key, error)


def gpg_getkeybyid(keyid, keyserver):
    """get gpg keyid from keyserver"""
    armour = gpg_export_armour(keyid)
    if not armour:
        try:
            gpg_recv_key(keyid, keyserver=keyserver)
            armour = gpg_export_armour(keyid)
        except ValueError:
            LOG.exception('Failed to obtain gpg key %s', keyid)
            raise
        finally:
            # delete just imported key to leave environment as it was before
            gpg_delete_key(keyid)

    return armour.rstrip('\n')
