# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import contextlib
import copy as obj_copy
import email
import glob
import grp
import gzip
import hashlib
import io
import json
import os
import os.path
import platform
import pwd
import random
import re
import shlex
import shutil
import socket
import stat
import string
import subprocess
import sys
import time
from base64 import b64decode, b64encode
from errno import ENOENT
from functools import lru_cache
from urllib import parse

from cloudinit import importer
from cloudinit import log as logging
from cloudinit import subp
from cloudinit import (
    mergers,
    safeyaml,
    temp_utils,
    type_utils,
    url_helper,
    version,
)
from cloudinit.settings import CFG_BUILTIN

_DNS_REDIRECT_IP = None
LOG = logging.getLogger(__name__)

# Helps cleanup filenames to ensure they aren't FS incompatible
FN_REPLACEMENTS = {
    os.sep: '_',
}
FN_ALLOWED = ('_-.()' + string.digits + string.ascii_letters)

TRUE_STRINGS = ('true', '1', 'on', 'yes')
FALSE_STRINGS = ('off', '0', 'no', 'false')


def kernel_version():
    return tuple(map(int, os.uname().release.split('.')[:2]))


@lru_cache()
def get_dpkg_architecture(target=None):
    """Return the sanitized string output by `dpkg --print-architecture`.

    N.B. This function is wrapped in functools.lru_cache, so repeated calls
    won't shell out every time.
    """
    out, _ = subp.subp(['dpkg', '--print-architecture'], capture=True,
                       target=target)
    return out.strip()


@lru_cache()
def lsb_release(target=None):
    fmap = {'Codename': 'codename', 'Description': 'description',
            'Distributor ID': 'id', 'Release': 'release'}

    data = {}
    try:
        out, _ = subp.subp(['lsb_release', '--all'], capture=True,
                           target=target)
        for line in out.splitlines():
            fname, _, val = line.partition(":")
            if fname in fmap:
                data[fmap[fname]] = val.strip()
        missing = [k for k in fmap.values() if k not in data]
        if len(missing):
            LOG.warning("Missing fields in lsb_release --all output: %s",
                        ','.join(missing))

    except subp.ProcessExecutionError as err:
        LOG.warning("Unable to get lsb_release --all: %s", err)
        data = dict((v, "UNAVAILABLE") for v in fmap.values())

    return data


def decode_binary(blob, encoding='utf-8'):
    # Converts a binary type into a text type using given encoding.
    if isinstance(blob, str):
        return blob
    return blob.decode(encoding)


def encode_text(text, encoding='utf-8'):
    # Converts a text string into a binary type using given encoding.
    if isinstance(text, bytes):
        return text
    return text.encode(encoding)


def b64d(source):
    # Base64 decode some data, accepting bytes or unicode/str, and returning
    # str/unicode if the result is utf-8 compatible, otherwise returning bytes.
    decoded = b64decode(source)
    try:
        return decoded.decode('utf-8')
    except UnicodeDecodeError:
        return decoded


def b64e(source):
    # Base64 encode some data, accepting bytes or unicode/str, and returning
    # str/unicode if the result is utf-8 compatible, otherwise returning bytes.
    if not isinstance(source, bytes):
        source = source.encode('utf-8')
    return b64encode(source).decode('utf-8')


def fully_decoded_payload(part):
    # In Python 3, decoding the payload will ironically hand us a bytes object.
    # 'decode' means to decode according to Content-Transfer-Encoding, not
    # according to any charset in the Content-Type.  So, if we end up with
    # bytes, first try to decode to str via CT charset, and failing that, try
    # utf-8 using surrogate escapes.
    cte_payload = part.get_payload(decode=True)
    if (part.get_content_maintype() == 'text' and
            isinstance(cte_payload, bytes)):
        charset = part.get_charset()
        if charset and charset.input_codec:
            encoding = charset.input_codec
        else:
            encoding = 'utf-8'
        return cte_payload.decode(encoding, 'surrogateescape')
    return cte_payload


class SeLinuxGuard(object):
    def __init__(self, path, recursive=False):
        # Late import since it might not always
        # be possible to use this
        try:
            self.selinux = importer.import_module('selinux')
        except ImportError:
            self.selinux = None
        self.path = path
        self.recursive = recursive

    def __enter__(self):
        if self.selinux and self.selinux.is_selinux_enabled():
            return True
        else:
            return False

    def __exit__(self, excp_type, excp_value, excp_traceback):
        if not self.selinux or not self.selinux.is_selinux_enabled():
            return
        if not os.path.lexists(self.path):
            return

        path = os.path.realpath(self.path)
        try:
            stats = os.lstat(path)
            self.selinux.matchpathcon(path, stats[stat.ST_MODE])
        except OSError:
            return

        LOG.debug("Restoring selinux mode for %s (recursive=%s)",
                  path, self.recursive)
        try:
            self.selinux.restorecon(path, recursive=self.recursive)
        except OSError as e:
            LOG.warning('restorecon failed on %s,%s maybe badness? %s',
                        path, self.recursive, e)


class MountFailedError(Exception):
    pass


class DecompressionError(Exception):
    pass


def fork_cb(child_cb, *args, **kwargs):
    fid = os.fork()
    if fid == 0:
        try:
            child_cb(*args, **kwargs)
            os._exit(0)
        except Exception:
            logexc(LOG, "Failed forking and calling callback %s",
                   type_utils.obj_name(child_cb))
            os._exit(1)
    else:
        LOG.debug("Forked child %s who will run callback %s",
                  fid, type_utils.obj_name(child_cb))


def is_true(val, addons=None):
    if isinstance(val, (bool)):
        return val is True
    check_set = TRUE_STRINGS
    if addons:
        check_set = list(check_set) + addons
    if str(val).lower().strip() in check_set:
        return True
    return False


def is_false(val, addons=None):
    if isinstance(val, (bool)):
        return val is False
    check_set = FALSE_STRINGS
    if addons:
        check_set = list(check_set) + addons
    if str(val).lower().strip() in check_set:
        return True
    return False


def translate_bool(val, addons=None):
    if not val:
        # This handles empty lists and false and
        # other things that python believes are false
        return False
    # If its already a boolean skip
    if isinstance(val, (bool)):
        return val
    return is_true(val, addons)


def rand_str(strlen=32, select_from=None):
    r = random.SystemRandom()
    if not select_from:
        select_from = string.ascii_letters + string.digits
    return "".join([r.choice(select_from) for _x in range(0, strlen)])


def rand_dict_key(dictionary, postfix=None):
    if not postfix:
        postfix = ""
    while True:
        newkey = rand_str(strlen=8) + "_" + postfix
        if newkey not in dictionary:
            break
    return newkey


def read_conf(fname):
    try:
        return load_yaml(load_file(fname), default={})
    except IOError as e:
        if e.errno == ENOENT:
            return {}
        else:
            raise


# Merges X lists, and then keeps the
# unique ones, but orders by sort order
# instead of by the original order
def uniq_merge_sorted(*lists):
    return sorted(uniq_merge(*lists))


# Merges X lists and then iterates over those
# and only keeps the unique items (order preserving)
# and returns that merged and uniqued list as the
# final result.
#
# Note: if any entry is a string it will be
# split on commas and empty entries will be
# evicted and merged in accordingly.
def uniq_merge(*lists):
    combined_list = []
    for a_list in lists:
        if isinstance(a_list, str):
            a_list = a_list.strip().split(",")
            # Kickout the empty ones
            a_list = [a for a in a_list if len(a)]
        combined_list.extend(a_list)
    return uniq_list(combined_list)


def clean_filename(fn):
    for (k, v) in FN_REPLACEMENTS.items():
        fn = fn.replace(k, v)
    removals = []
    for k in fn:
        if k not in FN_ALLOWED:
            removals.append(k)
    for k in removals:
        fn = fn.replace(k, '')
    fn = fn.strip()
    return fn


def decomp_gzip(data, quiet=True, decode=True):
    try:
        buf = io.BytesIO(encode_text(data))
        with contextlib.closing(gzip.GzipFile(None, "rb", 1, buf)) as gh:
            # E1101 is https://github.com/PyCQA/pylint/issues/1444
            if decode:
                return decode_binary(gh.read())  # pylint: disable=E1101
            else:
                return gh.read()  # pylint: disable=E1101
    except Exception as e:
        if quiet:
            return data
        else:
            raise DecompressionError(str(e)) from e


def extract_usergroup(ug_pair):
    if not ug_pair:
        return (None, None)
    ug_parted = ug_pair.split(':', 1)
    u = ug_parted[0].strip()
    if len(ug_parted) == 2:
        g = ug_parted[1].strip()
    else:
        g = None
    if not u or u == "-1" or u.lower() == "none":
        u = None
    if not g or g == "-1" or g.lower() == "none":
        g = None
    return (u, g)


def find_modules(root_dir):
    entries = dict()
    for fname in glob.glob(os.path.join(root_dir, "*.py")):
        if not os.path.isfile(fname):
            continue
        modname = os.path.basename(fname)[0:-3]
        modname = modname.strip()
        if modname and modname.find(".") == -1:
            entries[fname] = modname
    return entries


def multi_log(text, console=True, stderr=True,
              log=None, log_level=logging.DEBUG):
    if stderr:
        sys.stderr.write(text)
    if console:
        conpath = "/dev/console"
        if os.path.exists(conpath):
            with open(conpath, 'w') as wfh:
                wfh.write(text)
                wfh.flush()
        else:
            # A container may lack /dev/console (arguably a container bug).  If
            # it does not exist, then write output to stdout.  this will result
            # in duplicate stderr and stdout messages if stderr was True.
            #
            # even though upstart or systemd might have set up output to go to
            # /dev/console, the user may have configured elsewhere via
            # cloud-config 'output'.  If there is /dev/console, messages will
            # still get there.
            sys.stdout.write(text)
    if log:
        if text[-1] == "\n":
            log.log(log_level, text[:-1])
        else:
            log.log(log_level, text)


@lru_cache()
def is_Linux():
    return 'Linux' in platform.system()


@lru_cache()
def is_BSD():
    return 'BSD' in platform.system()


@lru_cache()
def is_FreeBSD():
    return system_info()['variant'] == "freebsd"


@lru_cache()
def is_NetBSD():
    return system_info()['variant'] == "netbsd"


@lru_cache()
def is_OpenBSD():
    return system_info()['variant'] == "openbsd"


def get_cfg_option_bool(yobj, key, default=False):
    if key not in yobj:
        return default
    return translate_bool(yobj[key])


def get_cfg_option_str(yobj, key, default=None):
    if key not in yobj:
        return default
    val = yobj[key]
    if not isinstance(val, str):
        val = str(val)
    return val


def get_cfg_option_int(yobj, key, default=0):
    return int(get_cfg_option_str(yobj, key, default=default))


def _parse_redhat_release(release_file=None):
    """Return a dictionary of distro info fields from /etc/redhat-release.

    Dict keys will align with /etc/os-release keys:
        ID, VERSION_ID, VERSION_CODENAME
    """

    if not release_file:
        release_file = '/etc/redhat-release'
    if not os.path.exists(release_file):
        return {}
    redhat_release = load_file(release_file)
    redhat_regex = (
        r'(?P<name>.+) release (?P<version>[\d\.]+) '
        r'\((?P<codename>[^)]+)\)')
    match = re.match(redhat_regex, redhat_release)
    if match:
        group = match.groupdict()
        group['name'] = group['name'].lower().partition(' linux')[0]
        if group['name'] == 'red hat enterprise':
            group['name'] = 'redhat'
        return {'ID': group['name'], 'VERSION_ID': group['version'],
                'VERSION_CODENAME': group['codename']}
    return {}


@lru_cache()
def get_linux_distro():
    distro_name = ''
    distro_version = ''
    flavor = ''
    os_release = {}
    if os.path.exists('/etc/os-release'):
        os_release = load_shell_content(load_file('/etc/os-release'))
    if not os_release:
        os_release = _parse_redhat_release()
    if os_release:
        distro_name = os_release.get('ID', '')
        distro_version = os_release.get('VERSION_ID', '')
        if 'sles' in distro_name or 'suse' in distro_name:
            # RELEASE_BLOCKER: We will drop this sles divergent behavior in
            # the future so that get_linux_distro returns a named tuple
            # which will include both version codename and architecture
            # on all distributions.
            flavor = platform.machine()
        else:
            flavor = os_release.get('VERSION_CODENAME', '')
            if not flavor:
                match = re.match(r'[^ ]+ \((?P<codename>[^)]+)\)',
                                 os_release.get('VERSION', ''))
                if match:
                    flavor = match.groupdict()['codename']
        if distro_name == 'rhel':
            distro_name = 'redhat'
    elif is_BSD():
        distro_name = platform.system().lower()
        distro_version = platform.release()
    else:
        dist = ('', '', '')
        try:
            # Was removed in 3.8
            dist = platform.dist()  # pylint: disable=W1505,E1101
        except Exception:
            pass
        finally:
            found = None
            for entry in dist:
                if entry:
                    found = 1
            if not found:
                LOG.warning('Unable to determine distribution, template '
                            'expansion may have unexpected results')
        return dist

    return (distro_name, distro_version, flavor)


@lru_cache()
def system_info():
    info = {
        'platform': platform.platform(),
        'system': platform.system(),
        'release': platform.release(),
        'python': platform.python_version(),
        'uname': list(platform.uname()),
        'dist': get_linux_distro()
    }
    system = info['system'].lower()
    var = 'unknown'
    if system == "linux":
        linux_dist = info['dist'][0].lower()
        if linux_dist in (
                'alpine', 'arch', 'centos', 'debian', 'fedora', 'rhel',
                'suse'):
            var = linux_dist
        elif linux_dist in ('ubuntu', 'linuxmint', 'mint'):
            var = 'ubuntu'
        elif linux_dist == 'redhat':
            var = 'rhel'
        elif linux_dist in (
                'opensuse', 'opensuse-tumbleweed', 'opensuse-leap',
                'sles', 'sle_hpc'):
            var = 'suse'
        else:
            var = 'linux'
    elif system in ('windows', 'darwin', "freebsd", "netbsd", "openbsd"):
        var = system

    info['variant'] = var

    return info


def get_cfg_option_list(yobj, key, default=None):
    """
    Gets the C{key} config option from C{yobj} as a list of strings. If the
    key is present as a single string it will be returned as a list with one
    string arg.

    @param yobj: The configuration object.
    @param key: The configuration key to get.
    @param default: The default to return if key is not found.
    @return: The configuration option as a list of strings or default if key
        is not found.
    """
    if key not in yobj:
        return default
    if yobj[key] is None:
        return []
    val = yobj[key]
    if isinstance(val, (list)):
        cval = [v for v in val]
        return cval
    if not isinstance(val, str):
        val = str(val)
    return [val]


# get a cfg entry by its path array
# for f['a']['b']: get_cfg_by_path(mycfg,('a','b'))
def get_cfg_by_path(yobj, keyp, default=None):
    """Return the value of the item at path C{keyp} in C{yobj}.

    example:
      get_cfg_by_path({'a': {'b': {'num': 4}}}, 'a/b/num') == 4
      get_cfg_by_path({'a': {'b': {'num': 4}}}, 'c/d') == None

    @param yobj: A dictionary.
    @param keyp: A path inside yobj.  it can be a '/' delimited string,
                 or an iterable.
    @param default: The default to return if the path does not exist.
    @return: The value of the item at keyp."
        is not found."""

    if isinstance(keyp, str):
        keyp = keyp.split("/")
    cur = yobj
    for tok in keyp:
        if tok not in cur:
            return default
        cur = cur[tok]
    return cur


def fixup_output(cfg, mode):
    (outfmt, errfmt) = get_output_cfg(cfg, mode)
    redirect_output(outfmt, errfmt)
    return (outfmt, errfmt)


# redirect_output(outfmt, errfmt, orig_out, orig_err)
#  replace orig_out and orig_err with filehandles specified in outfmt or errfmt
#  fmt can be:
#   > FILEPATH
#   >> FILEPATH
#   | program [ arg1 [ arg2 [ ... ] ] ]
#
#   with a '|', arguments are passed to shell, so one level of
#   shell escape is required.
#
#   if _CLOUD_INIT_SAVE_STDOUT is set in environment to a non empty and true
#   value then output input will not be closed (useful for debugging).
#
def redirect_output(outfmt, errfmt, o_out=None, o_err=None):

    if is_true(os.environ.get("_CLOUD_INIT_SAVE_STDOUT")):
        LOG.debug("Not redirecting output due to _CLOUD_INIT_SAVE_STDOUT")
        return

    if not o_out:
        o_out = sys.stdout
    if not o_err:
        o_err = sys.stderr

    if outfmt:
        LOG.debug("Redirecting %s to %s", o_out, outfmt)
        (mode, arg) = outfmt.split(" ", 1)
        if mode == ">" or mode == ">>":
            owith = "ab"
            if mode == ">":
                owith = "wb"
            new_fp = open(arg, owith)
        elif mode == "|":
            proc = subprocess.Popen(arg, shell=True, stdin=subprocess.PIPE)
            new_fp = proc.stdin
        else:
            raise TypeError("Invalid type for output format: %s" % outfmt)

        if o_out:
            os.dup2(new_fp.fileno(), o_out.fileno())

        if errfmt == outfmt:
            LOG.debug("Redirecting %s to %s", o_err, outfmt)
            os.dup2(new_fp.fileno(), o_err.fileno())
            return

    if errfmt:
        LOG.debug("Redirecting %s to %s", o_err, errfmt)
        (mode, arg) = errfmt.split(" ", 1)
        if mode == ">" or mode == ">>":
            owith = "ab"
            if mode == ">":
                owith = "wb"
            new_fp = open(arg, owith)
        elif mode == "|":
            proc = subprocess.Popen(arg, shell=True, stdin=subprocess.PIPE)
            new_fp = proc.stdin
        else:
            raise TypeError("Invalid type for error format: %s" % errfmt)

        if o_err:
            os.dup2(new_fp.fileno(), o_err.fileno())


def make_url(scheme, host, port=None,
             path='', params='', query='', fragment=''):

    pieces = [scheme or '']

    netloc = ''
    if host:
        netloc = str(host)

    if port is not None:
        netloc += ":" + "%s" % (port)

    pieces.append(netloc or '')
    pieces.append(path or '')
    pieces.append(params or '')
    pieces.append(query or '')
    pieces.append(fragment or '')

    return parse.urlunparse(pieces)


def mergemanydict(srcs, reverse=False):
    if reverse:
        srcs = reversed(srcs)
    merged_cfg = {}
    for cfg in srcs:
        if cfg:
            # Figure out which mergers to apply...
            mergers_to_apply = mergers.dict_extract_mergers(cfg)
            if not mergers_to_apply:
                mergers_to_apply = mergers.default_mergers()
            merger = mergers.construct(mergers_to_apply)
            merged_cfg = merger.merge(merged_cfg, cfg)
    return merged_cfg


@contextlib.contextmanager
def chdir(ndir):
    curr = os.getcwd()
    try:
        os.chdir(ndir)
        yield ndir
    finally:
        os.chdir(curr)


@contextlib.contextmanager
def umask(n_msk):
    old = os.umask(n_msk)
    try:
        yield old
    finally:
        os.umask(old)


def center(text, fill, max_len):
    return '{0:{fill}{align}{size}}'.format(text, fill=fill,
                                            align="^", size=max_len)


def del_dir(path):
    LOG.debug("Recursively deleting %s", path)
    shutil.rmtree(path)


# read_optional_seed
# returns boolean indicating success or failure (presense of files)
# if files are present, populates 'fill' dictionary with 'user-data' and
# 'meta-data' entries
def read_optional_seed(fill, base="", ext="", timeout=5):
    try:
        (md, ud, vd) = read_seeded(base, ext, timeout)
        fill['user-data'] = ud
        fill['vendor-data'] = vd
        fill['meta-data'] = md
        return True
    except url_helper.UrlError as e:
        if e.code == url_helper.NOT_FOUND:
            return False
        raise


def fetch_ssl_details(paths=None):
    ssl_details = {}
    # Lookup in these locations for ssl key/cert files
    ssl_cert_paths = [
        '/var/lib/cloud/data/ssl',
        '/var/lib/cloud/instance/data/ssl',
    ]
    if paths:
        ssl_cert_paths.extend([
            os.path.join(paths.get_ipath_cur('data'), 'ssl'),
            os.path.join(paths.get_cpath('data'), 'ssl'),
        ])
    ssl_cert_paths = uniq_merge(ssl_cert_paths)
    ssl_cert_paths = [d for d in ssl_cert_paths if d and os.path.isdir(d)]
    cert_file = None
    for d in ssl_cert_paths:
        if os.path.isfile(os.path.join(d, 'cert.pem')):
            cert_file = os.path.join(d, 'cert.pem')
            break
    key_file = None
    for d in ssl_cert_paths:
        if os.path.isfile(os.path.join(d, 'key.pem')):
            key_file = os.path.join(d, 'key.pem')
            break
    if cert_file and key_file:
        ssl_details['cert_file'] = cert_file
        ssl_details['key_file'] = key_file
    elif cert_file:
        ssl_details['cert_file'] = cert_file
    return ssl_details


def load_yaml(blob, default=None, allowed=(dict,)):
    loaded = default
    blob = decode_binary(blob)
    try:
        LOG.debug("Attempting to load yaml from string "
                  "of length %s with allowed root types %s",
                  len(blob), allowed)
        converted = safeyaml.load(blob)
        if converted is None:
            LOG.debug("loaded blob returned None, returning default.")
            converted = default
        elif not isinstance(converted, allowed):
            # Yes this will just be caught, but thats ok for now...
            raise TypeError(("Yaml load allows %s root types,"
                             " but got %s instead") %
                            (allowed, type_utils.obj_name(converted)))
        loaded = converted
    except (safeyaml.YAMLError, TypeError, ValueError) as e:
        msg = 'Failed loading yaml blob'
        mark = None
        if hasattr(e, 'context_mark') and getattr(e, 'context_mark'):
            mark = getattr(e, 'context_mark')
        elif hasattr(e, 'problem_mark') and getattr(e, 'problem_mark'):
            mark = getattr(e, 'problem_mark')
        if mark:
            msg += (
                '. Invalid format at line {line} column {col}: "{err}"'.format(
                    line=mark.line + 1, col=mark.column + 1, err=e))
        else:
            msg += '. {err}'.format(err=e)
        LOG.warning(msg)
    return loaded


def read_seeded(base="", ext="", timeout=5, retries=10, file_retries=0):
    if base.find("%s") >= 0:
        ud_url = base % ("user-data" + ext)
        vd_url = base % ("vendor-data" + ext)
        md_url = base % ("meta-data" + ext)
    else:
        ud_url = "%s%s%s" % (base, "user-data", ext)
        vd_url = "%s%s%s" % (base, "vendor-data", ext)
        md_url = "%s%s%s" % (base, "meta-data", ext)

    md_resp = url_helper.read_file_or_url(md_url, timeout=timeout,
                                          retries=retries)
    md = None
    if md_resp.ok():
        md = load_yaml(decode_binary(md_resp.contents), default={})

    ud_resp = url_helper.read_file_or_url(ud_url, timeout=timeout,
                                          retries=retries)
    ud = None
    if ud_resp.ok():
        ud = ud_resp.contents

    vd = None
    try:
        vd_resp = url_helper.read_file_or_url(vd_url, timeout=timeout,
                                              retries=retries)
    except url_helper.UrlError as e:
        LOG.debug("Error in vendor-data response: %s", e)
    else:
        if vd_resp.ok():
            vd = vd_resp.contents
        else:
            LOG.debug("Error in vendor-data response")

    return (md, ud, vd)


def read_conf_d(confd):
    # Get reverse sorted list (later trumps newer)
    confs = sorted(os.listdir(confd), reverse=True)

    # Remove anything not ending in '.cfg'
    confs = [f for f in confs if f.endswith(".cfg")]

    # Remove anything not a file
    confs = [f for f in confs
             if os.path.isfile(os.path.join(confd, f))]

    # Load them all so that they can be merged
    cfgs = []
    for fn in confs:
        cfgs.append(read_conf(os.path.join(confd, fn)))

    return mergemanydict(cfgs)


def read_conf_with_confd(cfgfile):
    cfg = read_conf(cfgfile)

    confd = False
    if "conf_d" in cfg:
        confd = cfg['conf_d']
        if confd:
            if not isinstance(confd, str):
                raise TypeError(("Config file %s contains 'conf_d' "
                                 "with non-string type %s") %
                                (cfgfile, type_utils.obj_name(confd)))
            else:
                confd = str(confd).strip()
    elif os.path.isdir("%s.d" % cfgfile):
        confd = "%s.d" % cfgfile

    if not confd or not os.path.isdir(confd):
        return cfg

    # Conf.d settings override input configuration
    confd_cfg = read_conf_d(confd)
    return mergemanydict([confd_cfg, cfg])


def read_conf_from_cmdline(cmdline=None):
    # return a dictionary of config on the cmdline or None
    return load_yaml(read_cc_from_cmdline(cmdline=cmdline))


def read_cc_from_cmdline(cmdline=None):
    # this should support reading cloud-config information from
    # the kernel command line.  It is intended to support content of the
    # format:
    #  cc: <yaml content here|urlencoded yaml content> [end_cc]
    # this would include:
    # cc: ssh_import_id: [smoser, kirkland]\\n
    # cc: ssh_import_id: [smoser, bob]\\nruncmd: [ [ ls, -l ], echo hi ] end_cc
    # cc:ssh_import_id: [smoser] end_cc cc:runcmd: [ [ ls, -l ] ] end_cc
    # cc:ssh_import_id: %5Bsmoser%5D end_cc
    if cmdline is None:
        cmdline = get_cmdline()

    tag_begin = "cc:"
    tag_end = "end_cc"
    begin_l = len(tag_begin)
    end_l = len(tag_end)
    clen = len(cmdline)
    tokens = []
    begin = cmdline.find(tag_begin)
    while begin >= 0:
        end = cmdline.find(tag_end, begin + begin_l)
        if end < 0:
            end = clen
        tokens.append(
            parse.unquote(
                cmdline[begin + begin_l:end].lstrip()).replace("\\n", "\n"))
        begin = cmdline.find(tag_begin, end + end_l)

    return '\n'.join(tokens)


def dos2unix(contents):
    # find first end of line
    pos = contents.find('\n')
    if pos <= 0 or contents[pos - 1] != '\r':
        return contents
    return contents.replace('\r\n', '\n')


def get_hostname_fqdn(cfg, cloud, metadata_only=False):
    """Get hostname and fqdn from config if present and fallback to cloud.

    @param cfg: Dictionary of merged user-data configuration (from init.cfg).
    @param cloud: Cloud instance from init.cloudify().
    @param metadata_only: Boolean, set True to only query cloud meta-data,
        returning None if not present in meta-data.
    @return: a Tuple of strings <hostname>, <fqdn>. Values can be none when
        metadata_only is True and no cfg or metadata provides hostname info.
    """
    if "fqdn" in cfg:
        # user specified a fqdn.  Default hostname then is based off that
        fqdn = cfg['fqdn']
        hostname = get_cfg_option_str(cfg, "hostname", fqdn.split('.')[0])
    else:
        if "hostname" in cfg and cfg['hostname'].find('.') > 0:
            # user specified hostname, and it had '.' in it
            # be nice to them.  set fqdn and hostname from that
            fqdn = cfg['hostname']
            hostname = cfg['hostname'][:fqdn.find('.')]
        else:
            # no fqdn set, get fqdn from cloud.
            # get hostname from cfg if available otherwise cloud
            fqdn = cloud.get_hostname(fqdn=True, metadata_only=metadata_only)
            if "hostname" in cfg:
                hostname = cfg['hostname']
            else:
                hostname = cloud.get_hostname(metadata_only=metadata_only)
    return (hostname, fqdn)


def get_fqdn_from_hosts(hostname, filename="/etc/hosts"):
    """
    For each host a single line should be present with
      the following information:

        IP_address canonical_hostname [aliases...]

      Fields of the entry are separated by any number of  blanks  and/or  tab
      characters.  Text  from a "#" character until the end of the line is a
      comment, and is ignored. Host  names  may  contain  only  alphanumeric
      characters, minus signs ("-"), and periods (".").  They must begin with
      an  alphabetic  character  and  end  with  an  alphanumeric  character.
      Optional aliases provide for name changes, alternate spellings, shorter
      hostnames, or generic hostnames (for example, localhost).
    """
    fqdn = None
    try:
        for line in load_file(filename).splitlines():
            hashpos = line.find("#")
            if hashpos >= 0:
                line = line[0:hashpos]
            line = line.strip()
            if not line:
                continue

            # If there there is less than 3 entries
            # (IP_address, canonical_hostname, alias)
            # then ignore this line
            toks = line.split()
            if len(toks) < 3:
                continue

            if hostname in toks[2:]:
                fqdn = toks[1]
                break
    except IOError:
        pass
    return fqdn


def is_resolvable(name):
    """determine if a url is resolvable, return a boolean
    This also attempts to be resilent against dns redirection.

    Note, that normal nsswitch resolution is used here.  So in order
    to avoid any utilization of 'search' entries in /etc/resolv.conf
    we have to append '.'.

    The top level 'invalid' domain is invalid per RFC.  And example.com
    should also not exist.  The '__cloud_init_expected_not_found__' entry will
    be resolved inside the search list.
    """
    global _DNS_REDIRECT_IP
    if _DNS_REDIRECT_IP is None:
        badips = set()
        badnames = ("does-not-exist.example.com.", "example.invalid.",
                    "__cloud_init_expected_not_found__")
        badresults = {}
        for iname in badnames:
            try:
                result = socket.getaddrinfo(iname, None, 0, 0,
                                            socket.SOCK_STREAM,
                                            socket.AI_CANONNAME)
                badresults[iname] = []
                for (_fam, _stype, _proto, cname, sockaddr) in result:
                    badresults[iname].append("%s: %s" % (cname, sockaddr[0]))
                    badips.add(sockaddr[0])
            except (socket.gaierror, socket.error):
                pass
        _DNS_REDIRECT_IP = badips
        if badresults:
            LOG.debug("detected dns redirection: %s", badresults)

    try:
        result = socket.getaddrinfo(name, None)
        # check first result's sockaddr field
        addr = result[0][4][0]
        if addr in _DNS_REDIRECT_IP:
            return False
        return True
    except (socket.gaierror, socket.error):
        return False


def get_hostname():
    hostname = socket.gethostname()
    return hostname


def gethostbyaddr(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except socket.herror:
        return None


def is_resolvable_url(url):
    """determine if this url is resolvable (existing or ip)."""
    return log_time(logfunc=LOG.debug, msg="Resolving URL: " + url,
                    func=is_resolvable,
                    args=(parse.urlparse(url).hostname,))


def search_for_mirror(candidates):
    """
    Search through a list of mirror urls for one that works
    This needs to return quickly.
    """
    if candidates is None:
        return None

    LOG.debug("search for mirror in candidates: '%s'", candidates)
    for cand in candidates:
        try:
            if is_resolvable_url(cand):
                LOG.debug("found working mirror: '%s'", cand)
                return cand
        except Exception:
            pass
    return None


def close_stdin():
    """
    reopen stdin as /dev/null so even subprocesses or other os level things get
    /dev/null as input.

    if _CLOUD_INIT_SAVE_STDIN is set in environment to a non empty and true
    value then input will not be closed (useful for debugging).
    """
    if is_true(os.environ.get("_CLOUD_INIT_SAVE_STDIN")):
        return
    with open(os.devnull) as fp:
        os.dup2(fp.fileno(), sys.stdin.fileno())


def find_devs_with_freebsd(criteria=None, oformat='device',
                           tag=None, no_cache=False, path=None):
    devlist = []
    if not criteria:
        return glob.glob("/dev/msdosfs/*") + glob.glob("/dev/iso9660/*")
    if criteria.startswith("LABEL="):
        label = criteria.lstrip("LABEL=")
        devlist = [
            p for p in ['/dev/msdosfs/' + label, '/dev/iso9660/' + label]
            if os.path.exists(p)]
    elif criteria == "TYPE=vfat":
        devlist = glob.glob("/dev/msdosfs/*")
    elif criteria == "TYPE=iso9660":
        devlist = glob.glob("/dev/iso9660/*")
    return devlist


def find_devs_with_netbsd(criteria=None, oformat='device',
                          tag=None, no_cache=False, path=None):
    devlist = []
    label = None
    _type = None
    if criteria:
        if criteria.startswith("LABEL="):
            label = criteria.lstrip("LABEL=")
        if criteria.startswith("TYPE="):
            _type = criteria.lstrip("TYPE=")
    out, _err = subp.subp(['sysctl', '-n', 'hw.disknames'], rcs=[0])
    for dev in out.split():
        if label or _type:
            mscdlabel_out, _ = subp.subp(['mscdlabel', dev], rcs=[0, 1])
        if label and not ('label "%s"' % label) in mscdlabel_out:
            continue
        if _type == "iso9660" and "ISO filesystem" not in mscdlabel_out:
            continue
        if _type == "vfat" and "ISO filesystem" in mscdlabel_out:
            continue
        devlist.append('/dev/' + dev)
    return devlist


def find_devs_with_openbsd(criteria=None, oformat='device',
                           tag=None, no_cache=False, path=None):
    out, _err = subp.subp(['sysctl', '-n', 'hw.disknames'], rcs=[0])
    devlist = []
    for entry in out.split(','):
        if not entry.endswith(':'):
            # ffs partition with a serial, not a config-drive
            continue
        if entry == 'fd0:':
            continue
        part_id = 'a' if entry.startswith('cd') else 'i'
        devlist.append(entry[:-1] + part_id)
    if criteria == "TYPE=iso9660":
        devlist = [i for i in devlist if i.startswith('cd')]
    elif criteria in ["LABEL=CONFIG-2", "TYPE=vfat"]:
        devlist = [i for i in devlist if not i.startswith('cd')]
    elif criteria:
        LOG.debug("Unexpected criteria: %s", criteria)
    return ['/dev/' + i for i in devlist]


def find_devs_with(criteria=None, oformat='device',
                   tag=None, no_cache=False, path=None):
    """
    find devices matching given criteria (via blkid)
    criteria can be *one* of:
      TYPE=<filesystem>
      LABEL=<label>
      UUID=<uuid>
    """
    if is_FreeBSD():
        return find_devs_with_freebsd(criteria, oformat,
                                      tag, no_cache, path)
    elif is_NetBSD():
        return find_devs_with_netbsd(criteria, oformat,
                                     tag, no_cache, path)
    elif is_OpenBSD():
        return find_devs_with_openbsd(criteria, oformat,
                                      tag, no_cache, path)

    blk_id_cmd = ['blkid']
    options = []
    if criteria:
        # Search for block devices with tokens named NAME that
        # have the value 'value' and display any devices which are found.
        # Common values for NAME include  TYPE, LABEL, and UUID.
        # If there are no devices specified on the command line,
        # all block devices will be searched; otherwise,
        # only search the devices specified by the user.
        options.append("-t%s" % (criteria))
    if tag:
        # For each (specified) device, show only the tags that match tag.
        options.append("-s%s" % (tag))
    if no_cache:
        # If you want to start with a clean cache
        # (i.e. don't report devices previously scanned
        # but not necessarily available at this time), specify /dev/null.
        options.extend(["-c", "/dev/null"])
    if oformat:
        # Display blkid's output using the specified format.
        # The format parameter may be:
        # full, value, list, device, udev, export
        options.append('-o%s' % (oformat))
    if path:
        options.append(path)
    cmd = blk_id_cmd + options
    # See man blkid for why 2 is added
    try:
        (out, _err) = subp.subp(cmd, rcs=[0, 2])
    except subp.ProcessExecutionError as e:
        if e.errno == ENOENT:
            # blkid not found...
            out = ""
        else:
            raise
    entries = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            entries.append(line)
    return entries


def blkid(devs=None, disable_cache=False):
    """Get all device tags details from blkid.

    @param devs: Optional list of device paths you wish to query.
    @param disable_cache: Bool, set True to start with clean cache.

    @return: Dict of key value pairs of info for the device.
    """
    if devs is None:
        devs = []
    else:
        devs = list(devs)

    cmd = ['blkid', '-o', 'full']
    if disable_cache:
        cmd.extend(['-c', '/dev/null'])
    cmd.extend(devs)

    # we have to decode with 'replace' as shelx.split (called by
    # load_shell_content) can't take bytes.  So this is potentially
    # lossy of non-utf-8 chars in blkid output.
    out, _ = subp.subp(cmd, capture=True, decode="replace")
    ret = {}
    for line in out.splitlines():
        dev, _, data = line.partition(":")
        ret[dev] = load_shell_content(data)
        ret[dev]["DEVNAME"] = dev

    return ret


def peek_file(fname, max_bytes):
    LOG.debug("Peeking at %s (max_bytes=%s)", fname, max_bytes)
    with open(fname, 'rb') as ifh:
        return ifh.read(max_bytes)


def uniq_list(in_list):
    out_list = []
    for i in in_list:
        if i in out_list:
            continue
        else:
            out_list.append(i)
    return out_list


def load_file(fname, read_cb=None, quiet=False, decode=True):
    LOG.debug("Reading from %s (quiet=%s)", fname, quiet)
    ofh = io.BytesIO()
    try:
        with open(fname, 'rb') as ifh:
            pipe_in_out(ifh, ofh, chunk_cb=read_cb)
    except IOError as e:
        if not quiet:
            raise
        if e.errno != ENOENT:
            raise
    contents = ofh.getvalue()
    LOG.debug("Read %s bytes from %s", len(contents), fname)
    if decode:
        return decode_binary(contents)
    else:
        return contents


@lru_cache()
def _get_cmdline():
    if is_container():
        try:
            contents = load_file("/proc/1/cmdline")
            # replace nulls with space and drop trailing null
            cmdline = contents.replace("\x00", " ")[:-1]
        except Exception as e:
            LOG.warning("failed reading /proc/1/cmdline: %s", e)
            cmdline = ""
    else:
        try:
            cmdline = load_file("/proc/cmdline").strip()
        except Exception:
            cmdline = ""

    return cmdline


def get_cmdline():
    if 'DEBUG_PROC_CMDLINE' in os.environ:
        return os.environ["DEBUG_PROC_CMDLINE"]

    return _get_cmdline()


def pipe_in_out(in_fh, out_fh, chunk_size=1024, chunk_cb=None):
    bytes_piped = 0
    while True:
        data = in_fh.read(chunk_size)
        if len(data) == 0:
            break
        else:
            out_fh.write(data)
            bytes_piped += len(data)
            if chunk_cb:
                chunk_cb(bytes_piped)
    out_fh.flush()
    return bytes_piped


def chownbyid(fname, uid=None, gid=None):
    if uid in [None, -1] and gid in [None, -1]:
        # Nothing to do
        return
    LOG.debug("Changing the ownership of %s to %s:%s", fname, uid, gid)
    os.chown(fname, uid, gid)


def chownbyname(fname, user=None, group=None):
    uid = -1
    gid = -1
    try:
        if user:
            uid = pwd.getpwnam(user).pw_uid
        if group:
            gid = grp.getgrnam(group).gr_gid
    except KeyError as e:
        raise OSError("Unknown user or group: %s" % (e)) from e
    chownbyid(fname, uid, gid)


# Always returns well formated values
# cfg is expected to have an entry 'output' in it, which is a dictionary
# that includes entries for 'init', 'config', 'final' or 'all'
#   init: /var/log/cloud.out
#   config: [ ">> /var/log/cloud-config.out", /var/log/cloud-config.err ]
#   final:
#     output: "| logger -p"
#     error: "> /dev/null"
# this returns the specific 'mode' entry, cleanly formatted, with value
def get_output_cfg(cfg, mode):
    ret = [None, None]
    if not cfg or 'output' not in cfg:
        return ret

    outcfg = cfg['output']
    if mode in outcfg:
        modecfg = outcfg[mode]
    else:
        if 'all' not in outcfg:
            return ret
        # if there is a 'all' item in the output list
        # then it applies to all users of this (init, config, final)
        modecfg = outcfg['all']

    # if value is a string, it specifies stdout and stderr
    if isinstance(modecfg, str):
        ret = [modecfg, modecfg]

    # if its a list, then we expect (stdout, stderr)
    if isinstance(modecfg, list):
        if len(modecfg) > 0:
            ret[0] = modecfg[0]
        if len(modecfg) > 1:
            ret[1] = modecfg[1]

    # if it is a dictionary, expect 'out' and 'error'
    # items, which indicate out and error
    if isinstance(modecfg, dict):
        if 'output' in modecfg:
            ret[0] = modecfg['output']
        if 'error' in modecfg:
            ret[1] = modecfg['error']

    # if err's entry == "&1", then make it same as stdout
    # as in shell syntax of "echo foo >/dev/null 2>&1"
    if ret[1] == "&1":
        ret[1] = ret[0]

    swlist = [">>", ">", "|"]
    for i in range(len(ret)):
        if not ret[i]:
            continue
        val = ret[i].lstrip()
        found = False
        for s in swlist:
            if val.startswith(s):
                val = "%s %s" % (s, val[len(s):].strip())
                found = True
                break
        if not found:
            # default behavior is append
            val = "%s %s" % (">>", val.strip())
        ret[i] = val

    return ret


def get_config_logfiles(cfg):
    """Return a list of log file paths from the configuration dictionary.

    @param cfg: The cloud-init merged configuration dictionary.
    """
    logs = []
    if not cfg or not isinstance(cfg, dict):
        return logs
    default_log = cfg.get('def_log_file')
    if default_log:
        logs.append(default_log)
    for fmt in get_output_cfg(cfg, None):
        if not fmt:
            continue
        match = re.match(r'(?P<type>\||>+)\s*(?P<target>.*)', fmt)
        if not match:
            continue
        target = match.group('target')
        parts = target.split()
        if len(parts) == 1:
            logs.append(target)
        elif ['tee', '-a'] == parts[:2]:
            logs.append(parts[2])
    return list(set(logs))


def logexc(log, msg, *args):
    # Setting this here allows this to change
    # levels easily (not always error level)
    # or even desirable to have that much junk
    # coming out to a non-debug stream
    if msg:
        log.warning(msg, *args)
    # Debug gets the full trace.  However, nose has a bug whereby its
    # logcapture plugin doesn't properly handle the case where there is no
    # actual exception.  To avoid tracebacks during the test suite then, we'll
    # do the actual exc_info extraction here, and if there is no exception in
    # flight, we'll just pass in None.
    exc_info = sys.exc_info()
    if exc_info == (None, None, None):
        exc_info = None
    log.debug(msg, exc_info=exc_info, *args)


def hash_blob(blob, routine, mlen=None):
    hasher = hashlib.new(routine)
    hasher.update(encode_text(blob))
    digest = hasher.hexdigest()
    # Don't get to long now
    if mlen is not None:
        return digest[0:mlen]
    else:
        return digest


def is_user(name):
    try:
        if pwd.getpwnam(name):
            return True
    except KeyError:
        return False


def is_group(name):
    try:
        if grp.getgrnam(name):
            return True
    except KeyError:
        return False


def rename(src, dest):
    LOG.debug("Renaming %s to %s", src, dest)
    # TODO(harlowja) use a se guard here??
    os.rename(src, dest)


def ensure_dirs(dirlist, mode=0o755):
    for d in dirlist:
        ensure_dir(d, mode)


def load_json(text, root_types=(dict,)):
    decoded = json.loads(decode_binary(text))
    if not isinstance(decoded, tuple(root_types)):
        expected_types = ", ".join([str(t) for t in root_types])
        raise TypeError("(%s) root types expected, got %s instead"
                        % (expected_types, type(decoded)))
    return decoded


def json_serialize_default(_obj):
    """Handler for types which aren't json serializable."""
    try:
        return 'ci-b64:{0}'.format(b64e(_obj))
    except AttributeError:
        return 'Warning: redacted unserializable type {0}'.format(type(_obj))


def json_preserialize_binary(data):
    """Preserialize any discovered binary values to avoid json.dumps issues.

    Used only on python 2.7 where default type handling is not honored for
    failure to encode binary data. LP: #1801364.
    TODO(Drop this function when py2.7 support is dropped from cloud-init)
    """
    data = obj_copy.deepcopy(data)
    for key, value in data.items():
        if isinstance(value, (dict)):
            data[key] = json_preserialize_binary(value)
        if isinstance(value, bytes):
            data[key] = 'ci-b64:{0}'.format(b64e(value))
    return data


def json_dumps(data):
    """Return data in nicely formatted json."""
    try:
        return json.dumps(
            data, indent=1, sort_keys=True, separators=(',', ': '),
            default=json_serialize_default)
    except UnicodeDecodeError:
        if sys.version_info[:2] == (2, 7):
            data = json_preserialize_binary(data)
            return json.dumps(data)
        raise


def ensure_dir(path, mode=None):
    if not os.path.isdir(path):
        # Make the dir and adjust the mode
        with SeLinuxGuard(os.path.dirname(path), recursive=True):
            os.makedirs(path)
        chmod(path, mode)
    else:
        # Just adjust the mode
        chmod(path, mode)


@contextlib.contextmanager
def unmounter(umount):
    try:
        yield umount
    finally:
        if umount:
            umount_cmd = ["umount", umount]
            subp.subp(umount_cmd)


def mounts():
    mounted = {}
    try:
        # Go through mounts to see what is already mounted
        if os.path.exists("/proc/mounts"):
            mount_locs = load_file("/proc/mounts").splitlines()
            method = 'proc'
        else:
            (mountoutput, _err) = subp.subp("mount")
            mount_locs = mountoutput.splitlines()
            method = 'mount'
        mountre = r'^(/dev/[\S]+) on (/.*) \((.+), .+, (.+)\)$'
        for mpline in mount_locs:
            # Linux: /dev/sda1 on /boot type ext4 (rw,relatime,data=ordered)
            # FreeBSD: /dev/vtbd0p2 on / (ufs, local, journaled soft-updates)
            try:
                if method == 'proc':
                    (dev, mp, fstype, opts, _freq, _passno) = mpline.split()
                else:
                    m = re.search(mountre, mpline)
                    dev = m.group(1)
                    mp = m.group(2)
                    fstype = m.group(3)
                    opts = m.group(4)
            except Exception:
                continue
            # If the name of the mount point contains spaces these
            # can be escaped as '\040', so undo that..
            mp = mp.replace("\\040", " ")
            mounted[dev] = {
                'fstype': fstype,
                'mountpoint': mp,
                'opts': opts,
            }
        LOG.debug("Fetched %s mounts from %s", mounted, method)
    except (IOError, OSError):
        logexc(LOG, "Failed fetching mount points")
    return mounted


def mount_cb(device, callback, data=None, mtype=None,
             update_env_for_mount=None):
    """
    Mount the device, call method 'callback' passing the directory
    in which it was mounted, then unmount.  Return whatever 'callback'
    returned.  If data != None, also pass data to callback.

    mtype is a filesystem type.  it may be a list, string (a single fsname)
    or a list of fsnames.
    """

    if isinstance(mtype, str):
        mtypes = [mtype]
    elif isinstance(mtype, (list, tuple)):
        mtypes = list(mtype)
    elif mtype is None:
        mtypes = None
    else:
        raise TypeError(
            'Unsupported type provided for mtype parameter: {_type}'.format(
                _type=type(mtype)))

    # clean up 'mtype' input a bit based on platform.
    if is_Linux():
        if mtypes is None:
            mtypes = ["auto"]
    elif is_BSD():
        if mtypes is None:
            mtypes = ['ufs', 'cd9660', 'msdos']
        for index, mtype in enumerate(mtypes):
            if mtype == "iso9660":
                mtypes[index] = "cd9660"
            if mtype in ["vfat", "msdosfs"]:
                mtypes[index] = "msdos"
    else:
        # we cannot do a smart "auto", so just call 'mount' once with no -t
        mtypes = ['']

    mounted = mounts()
    with temp_utils.tempdir() as tmpd:
        umount = False
        if os.path.realpath(device) in mounted:
            mountpoint = mounted[os.path.realpath(device)]['mountpoint']
        else:
            failure_reason = None
            for mtype in mtypes:
                mountpoint = None
                try:
                    mountcmd = ['mount', '-o', 'ro']
                    if mtype:
                        mountcmd.extend(['-t', mtype])
                    mountcmd.append(device)
                    mountcmd.append(tmpd)
                    subp.subp(mountcmd, update_env=update_env_for_mount)
                    umount = tmpd  # This forces it to be unmounted (when set)
                    mountpoint = tmpd
                    break
                except (IOError, OSError) as exc:
                    LOG.debug("Failed mount of '%s' as '%s': %s",
                              device, mtype, exc)
                    failure_reason = exc
            if not mountpoint:
                raise MountFailedError("Failed mounting %s to %s due to: %s" %
                                       (device, tmpd, failure_reason))

        # Be nice and ensure it ends with a slash
        if not mountpoint.endswith("/"):
            mountpoint += "/"
        with unmounter(umount):
            if data is None:
                ret = callback(mountpoint)
            else:
                ret = callback(mountpoint, data)
            return ret


def get_builtin_cfg():
    # Deep copy so that others can't modify
    return obj_copy.deepcopy(CFG_BUILTIN)


def is_link(path):
    LOG.debug("Testing if a link exists for %s", path)
    return os.path.islink(path)


def sym_link(source, link, force=False):
    LOG.debug("Creating symbolic link from %r => %r", link, source)
    if force and os.path.exists(link):
        del_file(link)
    os.symlink(source, link)


def del_file(path):
    LOG.debug("Attempting to remove %s", path)
    try:
        os.unlink(path)
    except OSError as e:
        if e.errno != ENOENT:
            raise e


def copy(src, dest):
    LOG.debug("Copying %s to %s", src, dest)
    shutil.copy(src, dest)


def time_rfc2822():
    try:
        ts = time.strftime("%a, %d %b %Y %H:%M:%S %z", time.gmtime())
    except Exception:
        ts = "??"
    return ts


@lru_cache()
def boottime():
    """Use sysctlbyname(3) via ctypes to find kern.boottime

    kern.boottime is of type struct timeval. Here we create a
    private class to easier unpack it.

    @return boottime: float to be compatible with linux
    """
    import ctypes
    import ctypes.util

    NULL_BYTES = b"\x00"

    class timeval(ctypes.Structure):
        _fields_ = [
            ("tv_sec", ctypes.c_int64),
            ("tv_usec", ctypes.c_int64)
        ]
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
    size = ctypes.c_size_t()
    size.value = ctypes.sizeof(timeval)
    buf = timeval()
    if libc.sysctlbyname(b"kern.boottime" + NULL_BYTES, ctypes.byref(buf),
                         ctypes.byref(size), None, 0) != -1:
        return buf.tv_sec + buf.tv_usec / 1000000.0
    raise RuntimeError("Unable to retrieve kern.boottime on this system")


def uptime():
    uptime_str = '??'
    method = 'unknown'
    try:
        if os.path.exists("/proc/uptime"):
            method = '/proc/uptime'
            contents = load_file("/proc/uptime")
            if contents:
                uptime_str = contents.split()[0]
        else:
            method = 'ctypes'
            # This is the *BSD codepath
            uptime_str = str(time.time() - boottime())

    except Exception:
        logexc(LOG, "Unable to read uptime using method: %s" % method)
    return uptime_str


def append_file(path, content):
    write_file(path, content, omode="ab", mode=None)


def ensure_file(
    path, mode: int = 0o644, *, preserve_mode: bool = False
) -> None:
    write_file(
        path, content='', omode="ab", mode=mode, preserve_mode=preserve_mode
    )


def safe_int(possible_int):
    try:
        return int(possible_int)
    except (ValueError, TypeError):
        return None


def chmod(path, mode):
    real_mode = safe_int(mode)
    if path and real_mode:
        with SeLinuxGuard(path):
            os.chmod(path, real_mode)


def write_file(
    filename,
    content,
    mode=0o644,
    omode="wb",
    preserve_mode=False,
    *,
    ensure_dir_exists=True
):
    """
    Writes a file with the given content and sets the file mode as specified.
    Restores the SELinux context if possible.

    @param filename: The full path of the file to write.
    @param content: The content to write to the file.
    @param mode: The filesystem mode to set on the file.
    @param omode: The open mode used when opening the file (w, wb, a, etc.)
    @param preserve_mode: If True and `filename` exists, preserve `filename`s
                          current mode instead of applying `mode`.
    @param ensure_dir_exists: If True (the default), ensure that the directory
                              containing `filename` exists before writing to
                              the file.
    """

    if preserve_mode:
        try:
            file_stat = os.stat(filename)
            mode = stat.S_IMODE(file_stat.st_mode)
        except OSError:
            pass

    if ensure_dir_exists:
        ensure_dir(os.path.dirname(filename))
    if 'b' in omode.lower():
        content = encode_text(content)
        write_type = 'bytes'
    else:
        content = decode_binary(content)
        write_type = 'characters'
    try:
        mode_r = "%o" % mode
    except TypeError:
        mode_r = "%r" % mode
    LOG.debug("Writing to %s - %s: [%s] %s %s",
              filename, omode, mode_r, len(content), write_type)
    with SeLinuxGuard(path=filename):
        with open(filename, omode) as fh:
            fh.write(content)
            fh.flush()
    chmod(filename, mode)


def delete_dir_contents(dirname):
    """
    Deletes all contents of a directory without deleting the directory itself.

    @param dirname: The directory whose contents should be deleted.
    """
    for node in os.listdir(dirname):
        node_fullpath = os.path.join(dirname, node)
        if os.path.isdir(node_fullpath):
            del_dir(node_fullpath)
        else:
            del_file(node_fullpath)


def make_header(comment_char="#", base='created'):
    ci_ver = version.version_string()
    header = str(comment_char)
    header += " %s by cloud-init v. %s" % (base.title(), ci_ver)
    header += " on %s" % time_rfc2822()
    return header


def abs_join(base, *paths):
    return os.path.abspath(os.path.join(base, *paths))


# shellify, takes a list of commands
#  for each entry in the list
#    if it is an array, shell protect it (with single ticks)
#    if it is a string, do nothing
def shellify(cmdlist, add_header=True):
    if not isinstance(cmdlist, (tuple, list)):
        raise TypeError(
            "Input to shellify was type '%s'. Expected list or tuple." %
            (type_utils.obj_name(cmdlist)))

    content = ''
    if add_header:
        content += "#!/bin/sh\n"
    escaped = "%s%s%s%s" % ("'", '\\', "'", "'")
    cmds_made = 0
    for args in cmdlist:
        # If the item is a list, wrap all items in single tick.
        # If its not, then just write it directly.
        if isinstance(args, (list, tuple)):
            fixed = []
            for f in args:
                fixed.append("'%s'" % (str(f).replace("'", escaped)))
            content = "%s%s\n" % (content, ' '.join(fixed))
            cmds_made += 1
        elif isinstance(args, str):
            content = "%s%s\n" % (content, args)
            cmds_made += 1
        else:
            raise TypeError(
                "Unable to shellify type '%s'. Expected list, string, tuple. "
                "Got: %s" % (type_utils.obj_name(args), args))

    LOG.debug("Shellified %s commands.", cmds_made)
    return content


def strip_prefix_suffix(line, prefix=None, suffix=None):
    if prefix and line.startswith(prefix):
        line = line[len(prefix):]
    if suffix and line.endswith(suffix):
        line = line[:-len(suffix)]
    return line


def _cmd_exits_zero(cmd):
    if subp.which(cmd[0]) is None:
        return False
    try:
        subp.subp(cmd)
    except subp.ProcessExecutionError:
        return False
    return True


def _is_container_systemd():
    return _cmd_exits_zero(["systemd-detect-virt", "--quiet", "--container"])


def _is_container_upstart():
    return _cmd_exits_zero(["running-in-container"])


def _is_container_old_lxc():
    return _cmd_exits_zero(["lxc-is-container"])


def _is_container_freebsd():
    if not is_FreeBSD():
        return False
    cmd = ["sysctl", "-qn", "security.jail.jailed"]
    if subp.which(cmd[0]) is None:
        return False
    out, _ = subp.subp(cmd)
    return out.strip() == "1"


@lru_cache()
def is_container():
    """
    Checks to see if this code running in a container of some sort
    """
    checks = (
        _is_container_systemd,
        _is_container_freebsd,
        _is_container_upstart,
        _is_container_old_lxc)

    for helper in checks:
        if helper():
            return True

    # this code is largely from the logic in
    # ubuntu's /etc/init/container-detect.conf
    try:
        # Detect old-style libvirt
        # Detect OpenVZ containers
        pid1env = get_proc_env(1)
        if "container" in pid1env:
            return True
        if "LIBVIRT_LXC_UUID" in pid1env:
            return True
    except (IOError, OSError):
        pass

    # Detect OpenVZ containers
    if os.path.isdir("/proc/vz") and not os.path.isdir("/proc/bc"):
        return True

    try:
        # Detect Vserver containers
        lines = load_file("/proc/self/status").splitlines()
        for line in lines:
            if line.startswith("VxID:"):
                (_key, val) = line.strip().split(":", 1)
                if val != "0":
                    return True
    except (IOError, OSError):
        pass

    return False


def is_lxd():
    """Check to see if we are running in a lxd container."""
    return os.path.exists('/dev/lxd/sock')


def get_proc_env(pid, encoding='utf-8', errors='replace'):
    """
    Return the environment in a dict that a given process id was started with.

    @param encoding: if true, then decoding will be done with
                     .decode(encoding, errors) and text will be returned.
                     if false then binary will be returned.
    @param errors:   only used if encoding is true."""
    fn = os.path.join("/proc", str(pid), "environ")

    try:
        contents = load_file(fn, decode=False)
    except (IOError, OSError):
        return {}

    env = {}
    null, equal = (b"\x00", b"=")
    if encoding:
        null, equal = ("\x00", "=")
        contents = contents.decode(encoding, errors)

    for tok in contents.split(null):
        if not tok:
            continue
        (name, val) = tok.split(equal, 1)
        if name:
            env[name] = val
    return env


def keyval_str_to_dict(kvstring):
    ret = {}
    for tok in kvstring.split():
        try:
            (key, val) = tok.split("=", 1)
        except ValueError:
            key = tok
            val = True
        ret[key] = val
    return ret


def is_partition(device):
    if device.startswith("/dev/"):
        device = device[5:]

    return os.path.isfile("/sys/class/block/%s/partition" % device)


def expand_package_list(version_fmt, pkgs):
    # we will accept tuples, lists of tuples, or just plain lists
    if not isinstance(pkgs, list):
        pkgs = [pkgs]

    pkglist = []
    for pkg in pkgs:
        if isinstance(pkg, str):
            pkglist.append(pkg)
            continue

        if isinstance(pkg, (tuple, list)):
            if len(pkg) < 1 or len(pkg) > 2:
                raise RuntimeError("Invalid package & version tuple.")

            if len(pkg) == 2 and pkg[1]:
                pkglist.append(version_fmt % tuple(pkg))
                continue

            pkglist.append(pkg[0])

        else:
            raise RuntimeError("Invalid package type.")

    return pkglist


def parse_mount_info(path, mountinfo_lines, log=LOG, get_mnt_opts=False):
    """Return the mount information for PATH given the lines from
    /proc/$$/mountinfo."""

    path_elements = [e for e in path.split('/') if e]
    devpth = None
    fs_type = None
    match_mount_point = None
    match_mount_point_elements = None
    for i, line in enumerate(mountinfo_lines):
        parts = line.split()

        # Completely fail if there is anything in any line that is
        # unexpected, as continuing to parse past a bad line could
        # cause an incorrect result to be returned, so it's better
        # return nothing than an incorrect result.

        # The minimum number of elements in a valid line is 10.
        if len(parts) < 10:
            log.debug("Line %d has two few columns (%d): %s",
                      i + 1, len(parts), line)
            return None

        mount_point = parts[4]
        mount_point_elements = [e for e in mount_point.split('/') if e]

        # Ignore mounts deeper than the path in question.
        if len(mount_point_elements) > len(path_elements):
            continue

        # Ignore mounts where the common path is not the same.
        x = min(len(mount_point_elements), len(path_elements))
        if mount_point_elements[0:x] != path_elements[0:x]:
            continue

        # Ignore mount points higher than an already seen mount
        # point.
        if (match_mount_point_elements is not None and
                len(match_mount_point_elements) > len(mount_point_elements)):
            continue

        # Find the '-' which terminates a list of optional columns to
        # find the filesystem type and the path to the device.  See
        # man 5 proc for the format of this file.
        try:
            i = parts.index('-')
        except ValueError:
            log.debug("Did not find column named '-' in line %d: %s",
                      i + 1, line)
            return None

        # Get the path to the device.
        try:
            fs_type = parts[i + 1]
            devpth = parts[i + 2]
        except IndexError:
            log.debug("Too few columns after '-' column in line %d: %s",
                      i + 1, line)
            return None

        match_mount_point = mount_point
        match_mount_point_elements = mount_point_elements
        mount_options = parts[5]

    if get_mnt_opts:
        if devpth and fs_type and match_mount_point and mount_options:
            return (devpth, fs_type, match_mount_point, mount_options)
    else:
        if devpth and fs_type and match_mount_point:
            return (devpth, fs_type, match_mount_point)

    return None


def parse_mtab(path):
    """On older kernels there's no /proc/$$/mountinfo, so use mtab."""
    for line in load_file("/etc/mtab").splitlines():
        devpth, mount_point, fs_type = line.split()[:3]
        if mount_point == path:
            return devpth, fs_type, mount_point
    return None


def find_freebsd_part(fs):
    splitted = fs.split('/')
    if len(splitted) == 3:
        return splitted[2]
    elif splitted[2] in ['label', 'gpt', 'ufs']:
        target_label = fs[5:]
        (part, _err) = subp.subp(['glabel', 'status', '-s'])
        for labels in part.split("\n"):
            items = labels.split()
            if len(items) > 0 and items[0] == target_label:
                part = items[2]
                break
        return str(part)
    else:
        LOG.warning("Unexpected input in find_freebsd_part: %s", fs)


def get_path_dev_freebsd(path, mnt_list):
    path_found = None
    for line in mnt_list.split("\n"):
        items = line.split()
        if (len(items) > 2 and os.path.exists(items[1] + path)):
            path_found = line
            break
    return path_found


def get_mount_info_freebsd(path):
    (result, err) = subp.subp(['mount', '-p', path], rcs=[0, 1])
    if len(err):
        # find a path if the input is not a mounting point
        (mnt_list, err) = subp.subp(['mount', '-p'])
        path_found = get_path_dev_freebsd(path, mnt_list)
        if (path_found is None):
            return None
        result = path_found
    ret = result.split()
    label_part = find_freebsd_part(ret[0])
    return "/dev/" + label_part, ret[2], ret[1]


def get_device_info_from_zpool(zpool):
    # zpool has 10 second timeout waiting for /dev/zfs LP: #1760173
    if not os.path.exists('/dev/zfs'):
        LOG.debug('Cannot get zpool info, no /dev/zfs')
        return None
    try:
        (zpoolstatus, err) = subp.subp(['zpool', 'status', zpool])
    except subp.ProcessExecutionError as err:
        LOG.warning("Unable to get zpool status of %s: %s", zpool, err)
        return None
    if len(err):
        return None
    r = r'.*(ONLINE).*'
    for line in zpoolstatus.split("\n"):
        if re.search(r, line) and zpool not in line and "state" not in line:
            disk = line.split()[0]
            LOG.debug('found zpool "%s" on disk %s', zpool, disk)
            return disk


def parse_mount(path):
    (mountoutput, _err) = subp.subp(['mount'])
    mount_locs = mountoutput.splitlines()
    # there are 2 types of mount outputs we have to parse therefore
    # the regex is a bit complex. to better understand this regex see:
    # https://regex101.com/r/2F6c1k/1
    # https://regex101.com/r/T2en7a/1
    regex = (r'^(/dev/[\S]+|.*zroot\S*?) on (/[\S]*) '
             r'(?=(?:type)[\s]+([\S]+)|\(([^,]*))')
    for line in mount_locs:
        m = re.search(regex, line)
        if not m:
            continue
        devpth = m.group(1)
        mount_point = m.group(2)
        # above regex will either fill the fs_type in group(3)
        # or group(4) depending on the format we have.
        fs_type = m.group(3)
        if fs_type is None:
            fs_type = m.group(4)
        LOG.debug('found line in mount -> devpth: %s, mount_point: %s, '
                  'fs_type: %s', devpth, mount_point, fs_type)
        # check whether the dev refers to a label on FreeBSD
        # for example, if dev is '/dev/label/rootfs', we should
        # continue finding the real device like '/dev/da0'.
        # this is only valid for non zfs file systems as a zpool
        # can have gpt labels as disk.
        devm = re.search('^(/dev/.+)p([0-9])$', devpth)
        if not devm and is_FreeBSD() and fs_type != 'zfs':
            return get_mount_info_freebsd(path)
        elif mount_point == path:
            return devpth, fs_type, mount_point
    return None


def get_mount_info(path, log=LOG, get_mnt_opts=False):
    # Use /proc/$$/mountinfo to find the device where path is mounted.
    # This is done because with a btrfs filesystem using os.stat(path)
    # does not return the ID of the device.
    #
    # Here, / has a device of 18 (decimal).
    #
    # $ stat /
    #   File: '/'
    #   Size: 234               Blocks: 0          IO Block: 4096   directory
    # Device: 12h/18d   Inode: 256         Links: 1
    # Access: (0755/drwxr-xr-x)  Uid: (    0/    root)   Gid: (    0/    root)
    # Access: 2013-01-13 07:31:04.358011255 +0000
    # Modify: 2013-01-13 18:48:25.930011255 +0000
    # Change: 2013-01-13 18:48:25.930011255 +0000
    #  Birth: -
    #
    # Find where / is mounted:
    #
    # $ mount | grep ' / '
    # /dev/vda1 on / type btrfs (rw,subvol=@,compress=lzo)
    #
    # And the device ID for /dev/vda1 is not 18:
    #
    # $ ls -l /dev/vda1
    # brw-rw---- 1 root disk 253, 1 Jan 13 08:29 /dev/vda1
    #
    # So use /proc/$$/mountinfo to find the device underlying the
    # input path.
    mountinfo_path = '/proc/%s/mountinfo' % os.getpid()
    if os.path.exists(mountinfo_path):
        lines = load_file(mountinfo_path).splitlines()
        return parse_mount_info(path, lines, log, get_mnt_opts)
    elif os.path.exists("/etc/mtab"):
        return parse_mtab(path)
    else:
        return parse_mount(path)


def log_time(logfunc, msg, func, args=None, kwargs=None, get_uptime=False):
    if args is None:
        args = []
    if kwargs is None:
        kwargs = {}

    start = time.time()

    ustart = None
    if get_uptime:
        try:
            ustart = float(uptime())
        except ValueError:
            pass

    try:
        ret = func(*args, **kwargs)
    finally:
        delta = time.time() - start
        udelta = None
        if ustart is not None:
            try:
                udelta = float(uptime()) - ustart
            except ValueError:
                pass

        tmsg = " took %0.3f seconds" % delta
        if get_uptime:
            if isinstance(udelta, (float)):
                tmsg += " (%0.2f)" % udelta
            else:
                tmsg += " (N/A)"
        try:
            logfunc(msg + tmsg)
        except Exception:
            pass
    return ret


def expand_dotted_devname(dotted):
    toks = dotted.rsplit(".", 1)
    if len(toks) > 1:
        return toks
    else:
        return (dotted, None)


def pathprefix2dict(base, required=None, optional=None, delim=os.path.sep):
    # return a dictionary populated with keys in 'required' and 'optional'
    # by reading files in prefix + delim + entry
    if required is None:
        required = []
    if optional is None:
        optional = []

    missing = []
    ret = {}
    for f in required + optional:
        try:
            ret[f] = load_file(base + delim + f, quiet=False, decode=False)
        except IOError as e:
            if e.errno != ENOENT:
                raise
            if f in required:
                missing.append(f)

    if len(missing):
        raise ValueError(
            'Missing required files: {files}'.format(files=','.join(missing)))

    return ret


def read_meminfo(meminfo="/proc/meminfo", raw=False):
    # read a /proc/meminfo style file and return
    # a dict with 'total', 'free', and 'available'
    mpliers = {'kB': 2 ** 10, 'mB': 2 ** 20, 'B': 1, 'gB': 2 ** 30}
    kmap = {'MemTotal:': 'total', 'MemFree:': 'free',
            'MemAvailable:': 'available'}
    ret = {}
    for line in load_file(meminfo).splitlines():
        try:
            key, value, unit = line.split()
        except ValueError:
            key, value = line.split()
            unit = 'B'
        if raw:
            ret[key] = int(value) * mpliers[unit]
        elif key in kmap:
            ret[kmap[key]] = int(value) * mpliers[unit]

    return ret


def human2bytes(size):
    """Convert human string or integer to size in bytes
      10M => 10485760
      .5G => 536870912
    """
    size_in = size
    if size.endswith("B"):
        size = size[:-1]

    mpliers = {'B': 1, 'K': 2 ** 10, 'M': 2 ** 20, 'G': 2 ** 30, 'T': 2 ** 40}

    num = size
    mplier = 'B'
    for m in mpliers:
        if size.endswith(m):
            mplier = m
            num = size[0:-len(m)]

    try:
        num = float(num)
    except ValueError as e:
        raise ValueError("'%s' is not valid input." % size_in) from e

    if num < 0:
        raise ValueError("'%s': cannot be negative" % size_in)

    return int(num * mpliers[mplier])


def is_x86(uname_arch=None):
    """Return True if platform is x86-based"""
    if uname_arch is None:
        uname_arch = os.uname()[4]
    x86_arch_match = (
        uname_arch == 'x86_64' or
        (uname_arch[0] == 'i' and uname_arch[2:] == '86'))
    return x86_arch_match


def message_from_string(string):
    if sys.version_info[:2] < (2, 7):
        return email.message_from_file(io.StringIO(string))
    return email.message_from_string(string)


def get_installed_packages(target=None):
    (out, _) = subp.subp(['dpkg-query', '--list'], target=target, capture=True)

    pkgs_inst = set()
    for line in out.splitlines():
        try:
            (state, pkg, _) = line.split(None, 2)
        except ValueError:
            continue
        if state.startswith("hi") or state.startswith("ii"):
            pkgs_inst.add(re.sub(":.*", "", pkg))

    return pkgs_inst


def system_is_snappy():
    # channel.ini is configparser loadable.
    # snappy will move to using /etc/system-image/config.d/*.ini
    # this is certainly not a perfect test, but good enough for now.
    orpath = "/etc/os-release"
    try:
        orinfo = load_shell_content(load_file(orpath, quiet=True))
        if orinfo.get('ID', '').lower() == "ubuntu-core":
            return True
    except ValueError as e:
        LOG.warning("Unexpected error loading '%s': %s", orpath, e)

    cmdline = get_cmdline()
    if 'snap_core=' in cmdline:
        return True

    content = load_file("/etc/system-image/channel.ini", quiet=True)
    if 'ubuntu-core' in content.lower():
        return True
    if os.path.isdir("/etc/system-image/config.d/"):
        return True
    return False


def indent(text, prefix):
    """replacement for indent from textwrap that is not available in 2.7."""
    lines = []
    for line in text.splitlines(True):
        lines.append(prefix + line)
    return ''.join(lines)


def rootdev_from_cmdline(cmdline):
    found = None
    for tok in cmdline.split():
        if tok.startswith("root="):
            found = tok[5:]
            break
    if found is None:
        return None

    if found.startswith("/dev/"):
        return found
    if found.startswith("LABEL="):
        return "/dev/disk/by-label/" + found[len("LABEL="):]
    if found.startswith("UUID="):
        return "/dev/disk/by-uuid/" + found[len("UUID="):].lower()
    if found.startswith("PARTUUID="):
        disks_path = ("/dev/disk/by-partuuid/" +
                      found[len("PARTUUID="):].lower())
        if os.path.exists(disks_path):
            return disks_path
        results = find_devs_with(found)
        if results:
            return results[0]
        # we know this doesn't exist, but for consistency return the path as
        # it /would/ exist
        return disks_path

    return "/dev/" + found


def load_shell_content(content, add_empty=False, empty_val=None):
    """Given shell like syntax (key=value\nkey2=value2\n) in content
       return the data in dictionary form.  If 'add_empty' is True
       then add entries in to the returned dictionary for 'VAR='
       variables.  Set their value to empty_val."""

    def _shlex_split(blob):
        return shlex.split(blob, comments=True)

    data = {}
    for line in _shlex_split(content):
        key, value = line.split("=", 1)
        if not value:
            value = empty_val
        if add_empty or value:
            data[key] = value

    return data


def wait_for_files(flist, maxwait, naplen=.5, log_pre=""):
    need = set(flist)
    waited = 0
    while True:
        need -= set([f for f in need if os.path.exists(f)])
        if len(need) == 0:
            LOG.debug("%sAll files appeared after %s seconds: %s",
                      log_pre, waited, flist)
            return []
        if waited == 0:
            LOG.debug("%sWaiting up to %s seconds for the following files: %s",
                      log_pre, maxwait, flist)
        if waited + naplen > maxwait:
            break
        time.sleep(naplen)
        waited += naplen

    LOG.debug("%sStill missing files after %s seconds: %s",
              log_pre, maxwait, need)
    return need


def mount_is_read_write(mount_point):
    """Check whether the given mount point is mounted rw"""
    result = get_mount_info(mount_point, get_mnt_opts=True)
    mount_opts = result[-1].split(',')
    return mount_opts[0] == 'rw'


def udevadm_settle(exists=None, timeout=None):
    """Invoke udevadm settle with optional exists and timeout parameters"""
    settle_cmd = ["udevadm", "settle"]
    if exists:
        # skip the settle if the requested path already exists
        if os.path.exists(exists):
            return
        settle_cmd.extend(['--exit-if-exists=%s' % exists])
    if timeout:
        settle_cmd.extend(['--timeout=%s' % timeout])

    return subp.subp(settle_cmd)


def get_proc_ppid(pid):
    """
    Return the parent pid of a process.
    """
    ppid = 0
    try:
        contents = load_file("/proc/%s/stat" % pid, quiet=True)
    except IOError as e:
        LOG.warning('Failed to load /proc/%s/stat. %s', pid, e)
    if contents:
        parts = contents.split(" ", 4)
        # man proc says
        #  ppid %d     (4) The PID of the parent.
        ppid = int(parts[3])
    return ppid

# vi: ts=4 expandtab
