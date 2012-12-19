# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

import sys

# Ensure this is aliased to a name not 'distros'
# since the module attribute 'distros'
# is a list of distros that are supported, not a sub-module
from cloudinit import distros as ds

from cloudinit import ssh_util
from cloudinit import util

from string import letters, digits  # pylint: disable=W0402

# We are removing certain 'painful' letters/numbers
PW_SET = (letters.translate(None, 'loLOI') +
          digits.translate(None, '01'))


def handle(_name, cfg, cloud, log, args):
    if len(args) != 0:
        # if run from command line, and give args, wipe the chpasswd['list']
        password = args[0]
        if 'chpasswd' in cfg and 'list' in cfg['chpasswd']:
            del cfg['chpasswd']['list']
    else:
        password = util.get_cfg_option_str(cfg, "password", None)

    expire = True
    pw_auth = "no"
    change_pwauth = False
    plist = None

    if 'chpasswd' in cfg:
        chfg = cfg['chpasswd']
        plist = util.get_cfg_option_str(chfg, 'list', plist)
        expire = util.get_cfg_option_bool(chfg, 'expire', expire)

    if not plist and password:
        (users, _groups) = ds.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ds.extract_default(users)
        if user:
            plist = "%s:%s" % (user, password)
        else:
            log.warn("No default or defined user to change password for.")

    errors = []
    if plist:
        plist_in = []
        randlist = []
        users = []
        for line in plist.splitlines():
            u, p = line.split(':', 1)
            if p == "R" or p == "RANDOM":
                p = rand_user_password()
                randlist.append("%s:%s" % (u, p))
            plist_in.append("%s:%s" % (u, p))
            users.append(u)

        ch_in = '\n'.join(plist_in)
        try:
            log.debug("Changing password for %s:", users)
            util.subp(['chpasswd'], ch_in)
        except Exception as e:
            errors.append(e)
            util.logexc(log,
                        "Failed to set passwords with chpasswd for %s", users)

        if len(randlist):
            blurb = ("Set the following 'random' passwords\n",
                     '\n'.join(randlist))
            sys.stderr.write("%s\n%s\n" % blurb)

        if expire:
            expired_users = []
            for u in users:
                try:
                    util.subp(['passwd', '--expire', u])
                    expired_users.append(u)
                except Exception as e:
                    errors.append(e)
                    util.logexc(log, "Failed to set 'expire' for %s", u)
            if expired_users:
                log.debug("Expired passwords for: %s users", expired_users)

    change_pwauth = False
    pw_auth = None
    if 'ssh_pwauth' in cfg:
        change_pwauth = True
        if util.is_true(cfg['ssh_pwauth']):
            pw_auth = 'yes'
        if util.is_false(cfg['ssh_pwauth']):
            pw_auth = 'no'

    if change_pwauth:
        replaced_auth = False

        # See: man sshd_config
        old_lines = ssh_util.parse_ssh_config(ssh_util.DEF_SSHD_CFG)
        new_lines = []
        i = 0
        for (i, line) in enumerate(old_lines):
            # Keywords are case-insensitive and arguments are case-sensitive
            if line.key == 'passwordauthentication':
                log.debug("Replacing auth line %s with %s", i + 1, pw_auth)
                replaced_auth = True
                line.value = pw_auth
            new_lines.append(line)

        if not replaced_auth:
            log.debug("Adding new auth line %s", i + 1)
            replaced_auth = True
            new_lines.append(ssh_util.SshdConfigLine('',
                                                     'PasswordAuthentication',
                                                     pw_auth))

        lines = [str(e) for e in new_lines]
        util.write_file(ssh_util.DEF_SSHD_CFG, "\n".join(lines))

        try:
            cmd = ['service']
            cmd.append(cloud.distro.get_option('ssh_svcname', 'ssh'))
            cmd.append('restart')
            util.subp(cmd)
            log.debug("Restarted the ssh daemon")
        except:
            util.logexc(log, "Restarting of the ssh daemon failed")

    if len(errors):
        log.debug("%s errors occured, re-raising the last one", len(errors))
        raise errors[-1]


def rand_user_password(pwlen=9):
    return util.rand_str(pwlen, select_from=PW_SET)
