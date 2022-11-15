# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Hafliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
import pwd

from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)

# See: man sshd_config
DEF_SSHD_CFG = "/etc/ssh/sshd_config"

# this list has been filtered out from keytypes of OpenSSH source
# openssh-8.3p1/sshkey.c:
# static const struct keytype keytypes[] = {
# filter out the keytypes with the sigonly flag, eg:
# { "rsa-sha2-256", "RSA", NULL, KEY_RSA, 0, 0, 1 },
# refer to the keytype struct of OpenSSH in the same file, to see
# if the position of the sigonly flag has been moved.
#
# dsa, rsa, ecdsa and ed25519 are added for legacy, as they are valid
# public keys in some old distros. They can possibly be removed
# in the future when support for the older distros is dropped
#
# When updating the list, also update the _is_printable_key list in
# cloudinit/config/cc_ssh_authkey_fingerprints.py
VALID_KEY_TYPES = (
    "dsa",
    "rsa",
    "ecdsa",
    "ed25519",
    "ecdsa-sha2-nistp256-cert-v01@openssh.com",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384-cert-v01@openssh.com",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521-cert-v01@openssh.com",
    "ecdsa-sha2-nistp521",
    "sk-ecdsa-sha2-nistp256-cert-v01@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
    "sk-ssh-ed25519-cert-v01@openssh.com",
    "sk-ssh-ed25519@openssh.com",
    "ssh-dss-cert-v01@openssh.com",
    "ssh-dss",
    "ssh-ed25519-cert-v01@openssh.com",
    "ssh-ed25519",
    "ssh-rsa-cert-v01@openssh.com",
    "ssh-rsa",
    "ssh-xmss-cert-v01@openssh.com",
    "ssh-xmss@openssh.com",
)

_DISABLE_USER_SSH_EXIT = 142

DISABLE_USER_OPTS = (
    "no-port-forwarding,no-agent-forwarding,"
    'no-X11-forwarding,command="echo \'Please login as the user \\"$USER\\"'
    ' rather than the user \\"$DISABLE_USER\\".\';echo;sleep 10;'
    "exit " + str(_DISABLE_USER_SSH_EXIT) + '"'
)


class AuthKeyLine:
    def __init__(
        self, source, keytype=None, base64=None, comment=None, options=None
    ):
        self.base64 = base64
        self.comment = comment
        self.options = options
        self.keytype = keytype
        self.source = source

    def valid(self):
        return self.base64 and self.keytype

    def __str__(self):
        toks = []
        if self.options:
            toks.append(self.options)
        if self.keytype:
            toks.append(self.keytype)
        if self.base64:
            toks.append(self.base64)
        if self.comment:
            toks.append(self.comment)
        if not toks:
            return self.source
        else:
            return " ".join(toks)


class AuthKeyLineParser:
    """
    AUTHORIZED_KEYS FILE FORMAT
     AuthorizedKeysFile specifies the file containing public keys for public
     key authentication; if none is specified, the default is
     ~/.ssh/authorized_keys.  Each line of the file contains one key (empty
     (because of the size of the public key encoding) up to a limit of 8 kilo-
     bytes, which permits DSA keys up to 8 kilobits and RSA keys up to 16
     kilobits.  You don't want to type them in; instead, copy the
     identity.pub, id_dsa.pub, or the id_rsa.pub file and edit it.

     sshd enforces a minimum RSA key modulus size for protocol 1 and protocol
     2 keys of 768 bits.

     The options (if present) consist of comma-separated option specifica-
     tions.  No spaces are permitted, except within double quotes.  The fol-
     lowing option specifications are supported (note that option keywords are
     case-insensitive):
    """

    def _extract_options(self, ent):
        """
        The options (if present) consist of comma-separated option specifica-
         tions.  No spaces are permitted, except within double quotes.
         Note that option keywords are case-insensitive.
        """
        quoted = False
        i = 0
        while i < len(ent) and ((quoted) or (ent[i] not in (" ", "\t"))):
            curc = ent[i]
            if i + 1 >= len(ent):
                i = i + 1
                break
            nextc = ent[i + 1]
            if curc == "\\" and nextc == '"':
                i = i + 1
            elif curc == '"':
                quoted = not quoted
            i = i + 1

        options = ent[0:i]

        # Return the rest of the string in 'remain'
        remain = ent[i:].lstrip()
        return (options, remain)

    def parse(self, src_line, options=None):
        # modeled after opensshes auth2-pubkey.c:user_key_allowed2
        line = src_line.rstrip("\r\n")
        if line.startswith("#") or line.strip() == "":
            return AuthKeyLine(src_line)

        def parse_ssh_key(ent):
            # return ketype, key, [comment]
            toks = ent.split(None, 2)
            if len(toks) < 2:
                raise TypeError("To few fields: %s" % len(toks))
            if toks[0] not in VALID_KEY_TYPES:
                raise TypeError("Invalid keytype %s" % toks[0])

            # valid key type and 2 or 3 fields:
            if len(toks) == 2:
                # no comment in line
                toks.append("")

            return toks

        ent = line.strip()
        try:
            (keytype, base64, comment) = parse_ssh_key(ent)
        except TypeError:
            (keyopts, remain) = self._extract_options(ent)
            if options is None:
                options = keyopts

            try:
                (keytype, base64, comment) = parse_ssh_key(remain)
            except TypeError:
                return AuthKeyLine(src_line)

        return AuthKeyLine(
            src_line,
            keytype=keytype,
            base64=base64,
            comment=comment,
            options=options,
        )


def parse_authorized_keys(fnames):
    lines = []
    parser = AuthKeyLineParser()
    contents = []
    for fname in fnames:
        try:
            if os.path.isfile(fname):
                lines = util.load_file(fname).splitlines()
                for line in lines:
                    contents.append(parser.parse(line))
        except (IOError, OSError):
            util.logexc(LOG, "Error reading lines from %s", fname)

    return contents


def update_authorized_keys(old_entries, keys):
    to_add = list([k for k in keys if k.valid()])
    for i in range(0, len(old_entries)):
        ent = old_entries[i]
        if not ent.valid():
            continue
        # Replace those with the same base64
        for k in keys:
            if k.base64 == ent.base64:
                # Replace it with our better one
                ent = k
                # Don't add it later
                if k in to_add:
                    to_add.remove(k)
        old_entries[i] = ent

    # Now append any entries we did not match above
    for key in to_add:
        old_entries.append(key)

    # Now format them back to strings...
    lines = [str(b) for b in old_entries]

    # Ensure it ends with a newline
    lines.append("")
    return "\n".join(lines)


def users_ssh_info(username):
    pw_ent = pwd.getpwnam(username)
    if not pw_ent or not pw_ent.pw_dir:
        raise RuntimeError("Unable to get SSH info for user %r" % (username))
    return (os.path.join(pw_ent.pw_dir, ".ssh"), pw_ent)


def render_authorizedkeysfile_paths(value, homedir, username):
    # The 'AuthorizedKeysFile' may contain tokens
    # of the form %T which are substituted during connection set-up.
    # The following tokens are defined: %% is replaced by a literal
    # '%', %h is replaced by the home directory of the user being
    # authenticated and %u is replaced by the username of that user.
    macros = (("%h", homedir), ("%u", username), ("%%", "%"))
    if not value:
        value = "%h/.ssh/authorized_keys"
    paths = value.split()
    rendered = []
    for path in paths:
        for macro, field in macros:
            path = path.replace(macro, field)
        if not path.startswith("/"):
            path = os.path.join(homedir, path)
        rendered.append(path)
    return rendered


# Inspired from safe_path() in openssh source code (misc.c).
def check_permissions(username, current_path, full_path, is_file, strictmodes):
    """Check if the file/folder in @current_path has the right permissions.

    We need to check that:
    1. If StrictMode is enabled, the owner is either root or the user
    2. the user can access the file/folder, otherwise ssh won't use it
    3. If StrictMode is enabled, no write permission is given to group
       and world users (022)
    """

    # group/world can only execute the folder (access)
    minimal_permissions = 0o711
    if is_file:
        # group/world can only read the file
        minimal_permissions = 0o644

    # 1. owner must be either root or the user itself
    owner = util.get_owner(current_path)
    if strictmodes and owner != username and owner != "root":
        LOG.debug(
            "Path %s in %s must be own by user %s or"
            " by root, but instead is own by %s. Ignoring key.",
            current_path,
            full_path,
            username,
            owner,
        )
        return False

    parent_permission = util.get_permissions(current_path)
    # 2. the user can access the file/folder, otherwise ssh won't use it
    if owner == username:
        # need only the owner permissions
        minimal_permissions &= 0o700
    else:
        group_owner = util.get_group(current_path)
        user_groups = util.get_user_groups(username)

        if group_owner in user_groups:
            # need only the group permissions
            minimal_permissions &= 0o070
        else:
            # need only the world permissions
            minimal_permissions &= 0o007

    if parent_permission & minimal_permissions == 0:
        LOG.debug(
            "Path %s in %s must be accessible by user %s,"
            " check its permissions",
            current_path,
            full_path,
            username,
        )
        return False

    # 3. no write permission (w) is given to group and world users (022)
    # Group and world user can still have +rx.
    if strictmodes and parent_permission & 0o022 != 0:
        LOG.debug(
            "Path %s in %s must not give write"
            "permission to group or world users. Ignoring key.",
            current_path,
            full_path,
        )
        return False

    return True


def check_create_path(username, filename, strictmodes):
    user_pwent = users_ssh_info(username)[1]
    root_pwent = users_ssh_info("root")[1]
    try:
        # check the directories first
        directories = filename.split("/")[1:-1]

        # scan in order, from root to file name
        parent_folder = ""
        # this is to comply also with unit tests, and
        # strange home directories
        home_folder = os.path.dirname(user_pwent.pw_dir)
        for directory in directories:
            parent_folder += "/" + directory

            # security check, disallow symlinks in the AuthorizedKeysFile path.
            if os.path.islink(parent_folder):
                LOG.debug(
                    "Invalid directory. Symlink exists in path: %s",
                    parent_folder,
                )
                return False

            if os.path.isfile(parent_folder):
                LOG.debug(
                    "Invalid directory. File exists in path: %s", parent_folder
                )
                return False

            if (
                home_folder.startswith(parent_folder)
                or parent_folder == user_pwent.pw_dir
            ):
                continue

            if not os.path.exists(parent_folder):
                # directory does not exist, and permission so far are good:
                # create the directory, and make it accessible by everyone
                # but owned by root, as it might be used by many users.
                with util.SeLinuxGuard(parent_folder):
                    mode = 0o755
                    uid = root_pwent.pw_uid
                    gid = root_pwent.pw_gid
                    if parent_folder.startswith(user_pwent.pw_dir):
                        mode = 0o700
                        uid = user_pwent.pw_uid
                        gid = user_pwent.pw_gid
                    os.makedirs(parent_folder, mode=mode, exist_ok=True)
                    util.chownbyid(parent_folder, uid, gid)

            permissions = check_permissions(
                username, parent_folder, filename, False, strictmodes
            )
            if not permissions:
                return False

        if os.path.islink(filename) or os.path.isdir(filename):
            LOG.debug("%s is not a file!", filename)
            return False

        # check the file
        if not os.path.exists(filename):
            # if file does not exist: we need to create it, since the
            # folders at this point exist and have right permissions
            util.write_file(filename, "", mode=0o600, ensure_dir_exists=True)
            util.chownbyid(filename, user_pwent.pw_uid, user_pwent.pw_gid)

        permissions = check_permissions(
            username, filename, filename, True, strictmodes
        )
        if not permissions:
            return False
    except (IOError, OSError) as e:
        util.logexc(LOG, str(e))
        return False

    return True


def extract_authorized_keys(username, sshd_cfg_file=DEF_SSHD_CFG):
    (ssh_dir, pw_ent) = users_ssh_info(username)
    default_authorizedkeys_file = os.path.join(ssh_dir, "authorized_keys")
    user_authorizedkeys_file = default_authorizedkeys_file
    auth_key_fns = []
    with util.SeLinuxGuard(ssh_dir, recursive=True):
        try:
            ssh_cfg = parse_ssh_config_map(sshd_cfg_file)
            key_paths = ssh_cfg.get(
                "authorizedkeysfile", "%h/.ssh/authorized_keys"
            )
            strictmodes = ssh_cfg.get("strictmodes", "yes")
            auth_key_fns = render_authorizedkeysfile_paths(
                key_paths, pw_ent.pw_dir, username
            )

        except (IOError, OSError):
            # Give up and use a default key filename
            auth_key_fns[0] = default_authorizedkeys_file
            util.logexc(
                LOG,
                "Failed extracting 'AuthorizedKeysFile' in SSH "
                "config from %r, using 'AuthorizedKeysFile' file "
                "%r instead",
                DEF_SSHD_CFG,
                auth_key_fns[0],
            )

    # check if one of the keys is the user's one and has the right permissions
    for key_path, auth_key_fn in zip(key_paths.split(), auth_key_fns):
        if any(
            [
                "%u" in key_path,
                "%h" in key_path,
                auth_key_fn.startswith("{}/".format(pw_ent.pw_dir)),
            ]
        ):
            permissions_ok = check_create_path(
                username, auth_key_fn, strictmodes == "yes"
            )
            if permissions_ok:
                user_authorizedkeys_file = auth_key_fn
                break

    if user_authorizedkeys_file != default_authorizedkeys_file:
        LOG.debug(
            "AuthorizedKeysFile has an user-specific authorized_keys, "
            "using %s",
            user_authorizedkeys_file,
        )

    return (
        user_authorizedkeys_file,
        parse_authorized_keys([user_authorizedkeys_file]),
    )


def setup_user_keys(keys, username, options=None):
    # Turn the 'update' keys given into actual entries
    parser = AuthKeyLineParser()
    key_entries = []
    for k in keys:
        key_entries.append(parser.parse(str(k), options=options))

    # Extract the old and make the new
    (auth_key_fn, auth_key_entries) = extract_authorized_keys(username)
    ssh_dir = os.path.dirname(auth_key_fn)
    with util.SeLinuxGuard(ssh_dir, recursive=True):
        content = update_authorized_keys(auth_key_entries, key_entries)
        util.write_file(auth_key_fn, content, preserve_mode=True)


class SshdConfigLine:
    def __init__(self, line, k=None, v=None):
        self.line = line
        self._key = k
        self.value = v

    @property
    def key(self):
        if self._key is None:
            return None
        # Keywords are case-insensitive
        return self._key.lower()

    def __str__(self):
        if self._key is None:
            return str(self.line)
        else:
            v = str(self._key)
            if self.value:
                v += " " + str(self.value)
            return v


def parse_ssh_config(fname):
    if not os.path.isfile(fname):
        return []
    return parse_ssh_config_lines(util.load_file(fname).splitlines())


def parse_ssh_config_lines(lines):
    # See: man sshd_config
    # The file contains keyword-argument pairs, one per line.
    # Lines starting with '#' and empty lines are interpreted as comments.
    # Note: key-words are case-insensitive and arguments are case-sensitive
    ret = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            ret.append(SshdConfigLine(line))
            continue
        try:
            key, val = line.split(None, 1)
        except ValueError:
            try:
                key, val = line.split("=", 1)
            except ValueError:
                LOG.debug(
                    'sshd_config: option "%s" has no key/value pair,'
                    " skipping it",
                    line,
                )
                continue
        ret.append(SshdConfigLine(line, key, val))
    return ret


def parse_ssh_config_map(fname):
    lines = parse_ssh_config(fname)
    if not lines:
        return {}
    ret = {}
    for line in lines:
        if not line.key:
            continue
        ret[line.key] = line.value
    return ret


def _includes_dconf(fname: str) -> bool:
    if not os.path.isfile(fname):
        return False
    with open(fname, "r") as f:
        for line in f:
            if line.startswith(f"Include {fname}.d/*.conf"):
                return True
    return False


def update_ssh_config(updates, fname=DEF_SSHD_CFG):
    """Read fname, and update if changes are necessary.

    @param updates: dictionary of desired values {Option: value}
    @return: boolean indicating if an update was done."""
    if _includes_dconf(fname):
        if not os.path.isdir(f"{fname}.d"):
            util.ensure_dir(f"{fname}.d", mode=0o755)
        fname = os.path.join(f"{fname}.d", "50-cloud-init.conf")
        if not os.path.isfile(fname):
            # Ensure root read-only:
            util.ensure_file(fname, 0o600)
    lines = parse_ssh_config(fname)
    changed = update_ssh_config_lines(lines=lines, updates=updates)
    if changed:
        util.write_file(
            fname,
            "\n".join([str(line) for line in lines]) + "\n",
            preserve_mode=True,
        )
    return len(changed) != 0


def update_ssh_config_lines(lines, updates):
    """Update the SSH config lines per updates.

    @param lines: array of SshdConfigLine.  This array is updated in place.
    @param updates: dictionary of desired values {Option: value}
    @return: A list of keys in updates that were changed."""
    found = set()
    changed = []

    # Keywords are case-insensitive and arguments are case-sensitive
    casemap = dict([(k.lower(), k) for k in updates.keys()])

    for (i, line) in enumerate(lines, start=1):
        if not line.key:
            continue
        if line.key in casemap:
            key = casemap[line.key]
            value = updates[key]
            found.add(key)
            if line.value == value:
                LOG.debug(
                    "line %d: option %s already set to %s", i, key, value
                )
            else:
                changed.append(key)
                LOG.debug(
                    "line %d: option %s updated %s -> %s",
                    i,
                    key,
                    line.value,
                    value,
                )
                line.value = value

    if len(found) != len(updates):
        for key, value in updates.items():
            if key in found:
                continue
            changed.append(key)
            lines.append(SshdConfigLine("", key, value))
            LOG.debug(
                "line %d: option %s added with %s", len(lines), key, value
            )
    return changed


# vi: ts=4 expandtab
