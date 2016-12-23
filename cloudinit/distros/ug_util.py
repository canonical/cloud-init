# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import six

from cloudinit import log as logging
from cloudinit import type_utils
from cloudinit import util

LOG = logging.getLogger(__name__)


# Normalizes a input group configuration
# which can be a comma seperated list of
# group names, or a list of group names
# or a python dictionary of group names
# to a list of members of that group.
#
# The output is a dictionary of group
# names => members of that group which
# is the standard form used in the rest
# of cloud-init
def _normalize_groups(grp_cfg):
    if isinstance(grp_cfg, six.string_types):
        grp_cfg = grp_cfg.strip().split(",")
    if isinstance(grp_cfg, list):
        c_grp_cfg = {}
        for i in grp_cfg:
            if isinstance(i, dict):
                for k, v in i.items():
                    if k not in c_grp_cfg:
                        if isinstance(v, list):
                            c_grp_cfg[k] = list(v)
                        elif isinstance(v, six.string_types):
                            c_grp_cfg[k] = [v]
                        else:
                            raise TypeError("Bad group member type %s" %
                                            type_utils.obj_name(v))
                    else:
                        if isinstance(v, list):
                            c_grp_cfg[k].extend(v)
                        elif isinstance(v, six.string_types):
                            c_grp_cfg[k].append(v)
                        else:
                            raise TypeError("Bad group member type %s" %
                                            type_utils.obj_name(v))
            elif isinstance(i, six.string_types):
                if i not in c_grp_cfg:
                    c_grp_cfg[i] = []
            else:
                raise TypeError("Unknown group name type %s" %
                                type_utils.obj_name(i))
        grp_cfg = c_grp_cfg
    groups = {}
    if isinstance(grp_cfg, dict):
        for (grp_name, grp_members) in grp_cfg.items():
            groups[grp_name] = util.uniq_merge_sorted(grp_members)
    else:
        raise TypeError(("Group config must be list, dict "
                         " or string types only and not %s") %
                        type_utils.obj_name(grp_cfg))
    return groups


# Normalizes a input group configuration
# which can be a comma seperated list of
# user names, or a list of string user names
# or a list of dictionaries with components
# that define the user config + 'name' (if
# a 'name' field does not exist then the
# default user is assumed to 'own' that
# configuration.
#
# The output is a dictionary of user
# names => user config which is the standard
# form used in the rest of cloud-init. Note
# the default user will have a special config
# entry 'default' which will be marked as true
# all other users will be marked as false.
def _normalize_users(u_cfg, def_user_cfg=None):
    if isinstance(u_cfg, dict):
        ad_ucfg = []
        for (k, v) in u_cfg.items():
            if isinstance(v, (bool, int, float) + six.string_types):
                if util.is_true(v):
                    ad_ucfg.append(str(k))
            elif isinstance(v, dict):
                v['name'] = k
                ad_ucfg.append(v)
            else:
                raise TypeError(("Unmappable user value type %s"
                                 " for key %s") % (type_utils.obj_name(v), k))
        u_cfg = ad_ucfg
    elif isinstance(u_cfg, six.string_types):
        u_cfg = util.uniq_merge_sorted(u_cfg)

    users = {}
    for user_config in u_cfg:
        if isinstance(user_config, (list,) + six.string_types):
            for u in util.uniq_merge(user_config):
                if u and u not in users:
                    users[u] = {}
        elif isinstance(user_config, dict):
            if 'name' in user_config:
                n = user_config.pop('name')
                prev_config = users.get(n) or {}
                users[n] = util.mergemanydict([prev_config,
                                               user_config])
            else:
                # Assume the default user then
                prev_config = users.get('default') or {}
                users['default'] = util.mergemanydict([prev_config,
                                                       user_config])
        else:
            raise TypeError(("User config must be dictionary/list "
                             " or string types only and not %s") %
                            type_utils.obj_name(user_config))

    # Ensure user options are in the right python friendly format
    if users:
        c_users = {}
        for (uname, uconfig) in users.items():
            c_uconfig = {}
            for (k, v) in uconfig.items():
                k = k.replace('-', '_').strip()
                if k:
                    c_uconfig[k] = v
            c_users[uname] = c_uconfig
        users = c_users

    # Fixup the default user into the real
    # default user name and replace it...
    def_user = None
    if users and 'default' in users:
        def_config = users.pop('default')
        if def_user_cfg:
            # Pickup what the default 'real name' is
            # and any groups that are provided by the
            # default config
            def_user_cfg = def_user_cfg.copy()
            def_user = def_user_cfg.pop('name')
            def_groups = def_user_cfg.pop('groups', [])
            # Pickup any config + groups for that user name
            # that we may have previously extracted
            parsed_config = users.pop(def_user, {})
            parsed_groups = parsed_config.get('groups', [])
            # Now merge our extracted groups with
            # anything the default config provided
            users_groups = util.uniq_merge_sorted(parsed_groups, def_groups)
            parsed_config['groups'] = ",".join(users_groups)
            # The real config for the default user is the
            # combination of the default user config provided
            # by the distro, the default user config provided
            # by the above merging for the user 'default' and
            # then the parsed config from the user's 'real name'
            # which does not have to be 'default' (but could be)
            users[def_user] = util.mergemanydict([def_user_cfg,
                                                  def_config,
                                                  parsed_config])

    # Ensure that only the default user that we
    # found (if any) is actually marked as being
    # the default user
    if users:
        for (uname, uconfig) in users.items():
            if def_user and uname == def_user:
                uconfig['default'] = True
            else:
                uconfig['default'] = False

    return users


# Normalizes a set of user/users and group
# dictionary configuration into a useable
# format that the rest of cloud-init can
# understand using the default user
# provided by the input distrobution (if any)
# to allow for mapping of the 'default' user.
#
# Output is a dictionary of group names -> [member] (list)
# and a dictionary of user names -> user configuration (dict)
#
# If 'user' exists it will override
# the 'users'[0] entry (if a list) otherwise it will
# just become an entry in the returned dictionary (no override)
def normalize_users_groups(cfg, distro):
    if not cfg:
        cfg = {}

    users = {}
    groups = {}
    if 'groups' in cfg:
        groups = _normalize_groups(cfg['groups'])

    # Handle the previous style of doing this where the first user
    # overrides the concept of the default user if provided in the user: XYZ
    # format.
    old_user = {}
    if 'user' in cfg and cfg['user']:
        old_user = cfg['user']
        # Translate it into the format that is more useful
        # going forward
        if isinstance(old_user, six.string_types):
            old_user = {
                'name': old_user,
            }
        if not isinstance(old_user, dict):
            LOG.warn(("Format for 'user' key must be a string or "
                      "dictionary and not %s"), type_utils.obj_name(old_user))
            old_user = {}

    # If no old user format, then assume the distro
    # provides what the 'default' user maps to, but notice
    # that if this is provided, we won't automatically inject
    # a 'default' user into the users list, while if a old user
    # format is provided we will.
    distro_user_config = {}
    try:
        distro_user_config = distro.get_default_user()
    except NotImplementedError:
        LOG.warn(("Distro has not implemented default user "
                  "access. No distribution provided default user"
                  " will be normalized."))

    # Merge the old user (which may just be an empty dict when not
    # present with the distro provided default user configuration so
    # that the old user style picks up all the distribution specific
    # attributes (if any)
    default_user_config = util.mergemanydict([old_user, distro_user_config])

    base_users = cfg.get('users', [])
    if not isinstance(base_users, (list, dict) + six.string_types):
        LOG.warn(("Format for 'users' key must be a comma separated string"
                  " or a dictionary or a list and not %s"),
                 type_utils.obj_name(base_users))
        base_users = []

    if old_user:
        # Ensure that when user: is provided that this user
        # always gets added (as the default user)
        if isinstance(base_users, list):
            # Just add it on at the end...
            base_users.append({'name': 'default'})
        elif isinstance(base_users, dict):
            base_users['default'] = dict(base_users).get('default', True)
        elif isinstance(base_users, six.string_types):
            # Just append it on to be re-parsed later
            base_users += ",default"

    users = _normalize_users(base_users, default_user_config)
    return (users, groups)


# Given a user dictionary config it will
# extract the default user name and user config
# from that list and return that tuple or
# return (None, None) if no default user is
# found in the given input
def extract_default(users, default_name=None, default_config=None):
    if not users:
        users = {}

    def safe_find(entry):
        config = entry[1]
        if not config or 'default' not in config:
            return False
        else:
            return config['default']

    tmp_users = users.items()
    tmp_users = dict(filter(safe_find, tmp_users))
    if not tmp_users:
        return (default_name, default_config)
    else:
        name = list(tmp_users)[0]
        config = tmp_users[name]
        config.pop('default', None)
        return (name, config)

# vi: ts=4 expandtab
