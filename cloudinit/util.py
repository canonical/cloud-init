# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Hafliger <juerg.haefliger@hp.com>
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

from StringIO import StringIO

import contextlib
import grp
import gzip
import os
import platform
import pwd
import shutil
import subprocess
import urlparse

import yaml

from cloudinit import log as logging
from cloudinit import url_helper as uhelp


try:
    import selinux
    HAVE_LIBSELINUX = True
except ImportError:
    HAVE_LIBSELINUX = False


LOG = logging.getLogger(__name__)

# Helps cleanup filenames to ensure they aren't FS incompatible
FN_REPLACEMENTS = {
    os.sep: '_',
}


class ProcessExecutionError(IOError):

    MESSAGE_TMPL = ('%(description)s\nCommand: %(cmd)s\n'
                    'Exit code: %(exit_code)s\nStdout: %(stdout)r\n'
                    'Stderr: %(stderr)r')

    def __init__(self, stdout=None, stderr=None,
                 exit_code=None, cmd=None,
                 description=None, reason=None):
        if not cmd:
            self.cmd = '-'
        else:
            self.cmd = cmd

        if not description:
            self.description = 'Unexpected error while running command.'
        else:
            self.description = description

        if not isinstance(exit_code, (long, int)):
            self.exit_code = '-'
        else:
            self.exit_code = exit_code

        if not stderr:
            self.stderr = ''
        else:
            self.stderr = stderr

        if not stdout:
            self.stdout = ''
        else:
            self.stdout = stdout

        message = self.MESSAGE_TMPL % {
            'description': self.description,
            'cmd': self.cmd,
            'exit_code': self.exit_code,
            'stdout': self.stdout,
            'stderr': self.stderr,
        }
        IOError.__init__(self, message)
        self.reason = reason


class _SeLinuxGuard(object):
    def __init__(self, path, recursive=False):
        self.path = path
        self.recursive = recursive
        self.engaged = False
        if HAVE_LIBSELINUX and selinux.is_selinux_enabled():
            self.engaged = True

    def __enter__(self):
        return self.engaged

    def __exit__(self, type, value, traceback):
        if self.engaged:
            LOG.debug("Disengaging selinux mode for %s: %s", self.path, self.recursive)
            selinux.restorecon(self.path, recursive=self.recursive)


def translate_bool(val):
    if not val:
        return False
    if val is isinstance(val, bool):
        return val
    if str(val).lower().strip() in ['true', '1', 'on', 'yes']:
        return True
    return False


def read_conf(fname):
    try:
        mp = yaml.load(load_file(fname))
        if not isinstance(mp, (dict)):
            return {}
        return mp
    except IOError as e:
        if e.errno == errno.ENOENT:
            return {}
        raise


def clean_filename(fn):
    for (k, v) in FN_REPLACEMENTS.items():
        fn = fn.replace(k, v)
    return fn.strip()


def decomp_str(data):
    try:
        uncomp = gzip.GzipFile(None, "rb", 1, StringIO(data)).read()
        return uncomp
    except:
        return data


def is_ipv4(instr):
    """ determine if input string is a ipv4 address. return boolean"""
    toks = instr.split('.')
    if len(toks) != 4:
        return False

    try:
        toks = [x for x in toks if (int(x) < 256 and int(x) > 0)]
    except:
        return False

    return (len(toks) == 4)


def get_base_cfg(cfgfile, cfg_builtin=None, parsed_cfgs=None):
    if parsed_cfgs and cfgfile in parsed_cfgs:
        return parsed_cfgs[cfgfile]

    syscfg = read_conf_with_confd(cfgfile)
    kern_contents = read_cc_from_cmdline()
    kerncfg = {}
    if kern_contents:
        kerncfg = yaml.load(kern_contents)

    # kernel parameters override system config
    combined = mergedict(kerncfg, syscfg)
    if cfg_builtin:
        fin = mergedict(combined, cfg_builtin)
    else:
        fin = combined

    # Cache it?
    if parsed_cfgs:
        parsed_cfgs[cfgfile] = fin
    return fin


def get_cfg_option_bool(yobj, key, default=False):
    if key not in yobj:
        return default
    return translate_bool(yobj[key])


def get_cfg_option_str(yobj, key, default=None):
    if key not in yobj:
        return default
    return yobj[key]


def system_info():
    return {
        'platform': platform.platform(),
        'release': platform.release(),
        'python': platform.python_version(),
        'uname': platform.uname(),
    }


def get_cfg_option_list_or_str(yobj, key, default=None):
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
    if not key in yobj:
        return default
    if yobj[key] is None:
        return []
    if isinstance(yobj[key], list):
        return yobj[key]
    return [yobj[key]]


# get a cfg entry by its path array
# for f['a']['b']: get_cfg_by_path(mycfg,('a','b'))
def get_cfg_by_path(yobj, keyp, default=None):
    cur = yobj
    for tok in keyp:
        if tok not in cur:
            return(default)
        cur = cur[tok]
    return cur


def mergedict(src, cand):
    """
    Merge values from C{cand} into C{src}. If C{src} has a key C{cand} will
    not override. Nested dictionaries are merged recursively.
    """
    if isinstance(src, dict) and isinstance(cand, dict):
        for k, v in cand.iteritems():
            if k not in src:
                src[k] = v
            else:
                src[k] = mergedict(src[k], v)
    else:
        if not isinstance(src, dict):
            raise TypeError("Attempting to merge a non dictionary source type: %s" % (type(src)))
        if not isinstance(cand, dict):
            raise TypeError("Attempting to merge a non dictionary candiate type: %s" % (type(cand)))
    return src


@contextlib.contextmanager
def tempdir(**kwargs):
    # This seems like it was only added in python 3.2
    # Make it since its useful...
    # See: http://bugs.python.org/file12970/tempdir.patch
    tdir = tempfile.mkdtemp(**kwargs)
    try:
        yield tdir
    finally:
        del_dir(tdir)


def del_dir(path):
    LOG.debug("Recursively deleting %s", path)
    shutil.rmtree(path)


# get keyid from keyserver
def getkeybyid(keyid, keyserver):
    shcmd = """
    k=${1} ks=${2};
    exec 2>/dev/null
    [ -n "$k" ] || exit 1;
    armour=$(gpg --list-keys --armour "${k}")
    if [ -z "${armour}" ]; then
       gpg --keyserver ${ks} --recv $k >/dev/null &&
          armour=$(gpg --export --armour "${k}") &&
          gpg --batch --yes --delete-keys "${k}"
    fi
    [ -n "${armour}" ] && echo "${armour}"
    """
    args = ['sh', '-c', shcmd, "export-gpg-keyid", keyid, keyserver]
    (stdout, stderr) = subp(args)
    return stdout


def runparts(dirp, skip_no_exist=True):
    if skip_no_exist and not os.path.isdir(dirp):
        return

    failed = 0
    attempted = 0
    for exe_name in sorted(os.listdir(dirp)):
        exe_path = os.path.join(dirp, exe_name)
        if os.path.isfile(exe_path) and os.access(exe_path, os.X_OK):
            attempted += 1
            try:
                subp([exe_path])
            except ProcessExecutionError as e:
                LOG.exception("Failed running %s [%i]", exe_path, e.exit_code)
                failed += 1

    if failed and attempted:
        raise RuntimeError('runparts: %i failures in %i attempted commands' % (failed, attempted))


# read_optional_seed
# returns boolean indicating success or failure (presense of files)
# if files are present, populates 'fill' dictionary with 'user-data' and
# 'meta-data' entries
def read_optional_seed(fill, base="", ext="", timeout=5):
    try:
        (md, ud) = read_seeded(base, ext, timeout)
        fill['user-data'] = ud
        fill['meta-data'] = md
        return True
    except OSError as e:
        if e.errno == errno.ENOENT:
            return False
        raise


def read_seeded(base="", ext="", timeout=5, retries=10, file_retries=0):
    if base.startswith("/"):
        base = "file://%s" % base

    # default retries for file is 0. for network is 10
    if base.startswith("file://"):
        retries = file_retries

    if base.find("%s") >= 0:
        ud_url = base % ("user-data" + ext)
        md_url = base % ("meta-data" + ext)
    else:
        ud_url = "%s%s%s" % (base, "user-data", ext)
        md_url = "%s%s%s" % (base, "meta-data", ext)

    (md_str, msc) = uhelp.readurl(md_url, timeout=timeout, retries=retries)
    (ud, usc) = uhelp.readurl(ud_url, timeout=timeout, retries=retries)
    md = None
    if md_str and uhelp.ok_http_code(msc):
        md = yaml.load(md_str)
    if not uhelp.ok_http_code(usc):
        ud = None
    return (md, ud)


def read_conf_d(confd):
    # get reverse sorted list (later trumps newer)
    confs = sorted(os.listdir(confd), reverse=True)

    # remove anything not ending in '.cfg'
    confs = [f for f in confs if f.endswith(".cfg")]

    # remove anything not a file
    confs = [f for f in confs if os.path.isfile(os.path.join(confd, f))]

    cfg = {}
    for conf in confs:
        cfg = mergedict(cfg, read_conf(os.path.join(confd, conf)))

    return cfg


def read_conf_with_confd(cfgfile):
    cfg = read_conf(cfgfile)

    confd = False
    if "conf_d" in cfg:
        if cfg['conf_d'] is not None:
            confd = cfg['conf_d']
            if not isinstance(confd, str):
                raise RuntimeError("cfgfile %s contains 'conf_d' "
                                "with non-string" % cfgfile)
    elif os.path.isdir("%s.d" % cfgfile):
        confd = "%s.d" % cfgfile

    if not confd:
        return cfg

    return mergedict(read_conf_d(confd), cfg)


def read_cc_from_cmdline(cmdline=None):
    # this should support reading cloud-config information from
    # the kernel command line.  It is intended to support content of the
    # format:
    #  cc: <yaml content here> [end_cc]
    # this would include:
    # cc: ssh_import_id: [smoser, kirkland]\\n
    # cc: ssh_import_id: [smoser, bob]\\nruncmd: [ [ ls, -l ], echo hi ] end_cc
    # cc:ssh_import_id: [smoser] end_cc cc:runcmd: [ [ ls, -l ] ] end_cc
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
        tokens.append(cmdline[begin + begin_l:end].lstrip().replace("\\n",
                                                                    "\n"))

        begin = cmdline.find(tag_begin, end + end_l)

    return '\n'.join(tokens)


def dos2unix(contents):
    # find first end of line
    pos = contents.find('\n')
    if pos <= 0 or contents[pos - 1] != '\r':
        return contents
    return contents.replace('\r\n', '\n')


def get_hostname_fqdn(cfg, cloud):
    # return the hostname and fqdn from 'cfg'.  If not found in cfg,
    # then fall back to data from cloud
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
            fqdn = cloud.get_hostname(fqdn=True)
            if "hostname" in cfg:
                hostname = cfg['hostname']
            else:
                hostname = cloud.get_hostname()
    return (hostname, fqdn)


def get_fqdn_from_hosts(hostname, filename="/etc/hosts"):
    # this parses /etc/hosts to get a fqdn.  It should return the same
    # result as 'hostname -f <hostname>' if /etc/hosts.conf
    # did not have did not have 'bind' in the order attribute
    fqdn = None
    try:
        for line in load_file(filename).splitlines():
            hashpos = line.find("#")
            if hashpos >= 0:
                line = line[0:hashpos]
            toks = line.split()
        
            # if there there is less than 3 entries (ip, canonical, alias)
            # then ignore this line
            if len(toks) < 3:
                continue
        
            if hostname in toks[2:]:
                fqdn = toks[1]
                break
    except IOError as e:
        pass
    return fqdn


def is_resolvable(name):
    """ determine if a url is resolvable, return a boolean """
    try:
        socket.getaddrinfo(name, None)
        return True
    except socket.gaierror:
        return False


def is_resolvable_url(url):
    """ determine if this url is resolvable (existing or ip) """
    return (is_resolvable(urlparse.urlparse(url).hostname))


def search_for_mirror(candidates):
    """ Search through a list of mirror urls for one that works """
    for cand in candidates:
        try:
            if is_resolvable_url(cand):
                return cand
        except Exception:
            pass
    return None


def close_stdin():
    """
    reopen stdin as /dev/null so even subprocesses or other os level things get
    /dev/null as input.

    if _CLOUD_INIT_SAVE_STDIN is set in environment to a non empty or '0' value
    then input will not be closed (only useful potentially for debugging).
    """
    if os.environ.get("_CLOUD_INIT_SAVE_STDIN") in ("", "0", 'False'):
        return
    with open(os.devnull) as fp:
        os.dup2(fp.fileno(), sys.stdin.fileno())


def find_devs_with(criteria):
    """
    find devices matching given criteria (via blkid)
    criteria can be *one* of:
      TYPE=<filesystem>
      LABEL=<label>
      UUID=<uuid>
    """
    try:
        (out, _err) = subp(['blkid', '-t%s' % criteria, '-odevice'])
    except ProcessExecutionError:
        return []
    return (out.splitlines())


def load_file(fname, read_cb=None):
    LOG.debug("Reading from %s", fname)
    with open(fname, 'rb') as fh:
        ofh = StringIO()
        pipe_in_out(fh, ofh, chunk_cb=read_cb)
        return ofh.getvalue()


def get_cmdline():
    if 'DEBUG_PROC_CMDLINE' in os.environ:
        cmdline = os.environ["DEBUG_PROC_CMDLINE"]
    else:
        try:
            cmdline = load_file("/proc/cmdline").strip()
        except:
            cmdline = ""
    return cmdline


def pipe_in_out(in_fh, out_fh, chunk_size=1024, chunk_cb=None):
    bytes_piped = 0
    LOG.debug("Transferring the contents of %s to %s in chunks of size %s.", in_fh, out_fh, chunk_size)
    while True:
        data = in_fh.read(chunk_size)
        if data == '':
            break
        else:
            out_fh.write(data)
            bytes_piped += len(data)
            if chunk_cb:
                chunk_cb(bytes_piped)
    out_fh.flush()
    return bytes_piped


def chownbyid(fname, uid=None, gid=None):
    if uid == None and gid == None:
        return
    LOG.debug("Changing the ownership of %s to %s:%s", fname, uid, gid)
    os.chown(fname, uid, gid)


def chownbyname(fname, user=None, group=None):
    uid = -1
    gid = -1
    if user:
        uid = pwd.getpwnam(user).pw_uid
    if group:
        gid = grp.getgrnam(group).gr_gid
    chownbyid(fname, uid, gid)


def ensure_dirs(dirlist, mode=0755):
    for d in dirlist:
        ensure_dir(d, mode)


def ensure_dir(path, mode=0755):
    if not os.path.isdir(path):
        fixmodes = []
        LOG.debug("Ensuring directory exists at path %s (perms=%s)", dir_name, mode)
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise e
        if mode is not None:
            os.chmod(path, mode)


def sym_link(source, link):
    LOG.debug("Creating symbolic link from %r => %r" % (link, source))
    os.symlink(source, link)


def del_file(path):
    LOG.debug("Attempting to remove %s", path)
    try:
        os.unlink(path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise e


def ensure_file(path):
    write_file(path, content='', omode="ab")


def write_file(filename, content, mode=0644, omode="wb"):
    """
    Writes a file with the given content and sets the file mode as specified.
    Resotres the SELinux context if possible.

    @param filename: The full path of the file to write.
    @param content: The content to write to the file.
    @param mode: The filesystem mode to set on the file.
    @param omode: The open mode used when opening the file (r, rb, a, etc.)
    """
    ensure_dir(os.path.dirname(filename))
    LOG.debug("Writing to %s - %s (perms=%s) %s bytes", filename, omode, mode, len(content))
    with open(filename, omode) as fh:
        with _SeLinuxGuard(filename):
            fh.write(content)
            fh.flush()
            if mode is not None:
                os.chmod(filename, mode)


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


def subp(args, input_data=None, allowed_rc=None, env=None):
    if allowed_rc is None:
        allowed_rc = [0]
    try:
        LOG.debug("Running command %s with allowed return codes %s", args, allowed_rc)
        sp = subprocess.Popen(args, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, stdin=subprocess.PIPE,
            env=env)
        (out, err) = sp.communicate(input_data)
    except OSError as e:
        raise ProcessExecutionError(cmd=args, reason=e)
    rc = sp.returncode
    if rc not in allowed_rc:
        raise ProcessExecutionError(stdout=out, stderr=err,
                                         exit_code=rc,
                                         cmd=args)
    # Just ensure blank instead of none??
    if not out:
        out = ''
    if not err:
        err = ''
    return (out, err)


# shellify, takes a list of commands
#  for each entry in the list
#    if it is an array, shell protect it (with single ticks)
#    if it is a string, do nothing
def shellify(cmdlist, add_header=True):
    content = ''
    if add_header:
        content += "#!/bin/sh\n"
    escaped = "%s%s%s%s" % ("'", '\\', "'", "'")
    for args in cmdlist:
        # if the item is a list, wrap all items in single tick
        # if its not, then just write it directly
        if isinstance(args, list):
            fixed = []
            for f in args:
                fixed.append("'%s'" % str(f).replace("'", escaped))
            content = "%s%s\n" % (content, ' '.join(fixed))
        else:
            content = "%s%s\n" % (content, str(args))
    return content


def is_container():
    # is this code running in a container of some sort

    for helper in ('running-in-container', 'lxc-is-container'):
        try:
            # try to run a helper program. if it returns true/zero
            # then we're inside a container. otherwise, no
            cmd = [helper]
            (stdout, stderr) = subp(cmd, allowed_rc=[0])
            return True
        except IOError as e:
            pass
            # Is this really needed?
            # if e.errno != errno.ENOENT:
            #     raise

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
    except IOError as e:
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
    except IOError as e:
        pass

    return False


def get_proc_env(pid):
    # return the environment in a dict that a given process id was started with
    env = {}
    fn = os.path.join("/proc/", str(pid), "environ")
    try:
        contents = load_file(fn)
        toks = contents.split("\0")
        for tok in toks:
            if tok == "":
                continue
            (name, val) = tok.split("=", 1)
            if not name:
                env[name] = val
    except IOError:
        pass
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
