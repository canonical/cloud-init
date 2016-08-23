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

import yaml
import os
import os.path
import shutil
import errno
import subprocess
from Cheetah.Template import Template
import urllib2
import urllib
import logging
import re
import socket
import sys
import time
import tempfile
import traceback
import urlparse

try:
    import selinux
    HAVE_LIBSELINUX = True
except ImportError:
    HAVE_LIBSELINUX = False


def read_conf(fname):
    try:
        stream = open(fname, "r")
        conf = yaml.load(stream)
        stream.close()
        return conf
    except IOError as e:
        if e.errno == errno.ENOENT:
            return {}
        raise


def get_base_cfg(cfgfile, cfg_builtin="", parsed_cfgs=None):
    kerncfg = {}
    syscfg = {}
    if parsed_cfgs and cfgfile in parsed_cfgs:
        return(parsed_cfgs[cfgfile])

    syscfg = read_conf_with_confd(cfgfile)

    kern_contents = read_cc_from_cmdline()
    if kern_contents:
        kerncfg = yaml.load(kern_contents)

    # kernel parameters override system config
    combined = mergedict(kerncfg, syscfg)

    if cfg_builtin:
        builtin = yaml.load(cfg_builtin)
        fin = mergedict(combined, builtin)
    else:
        fin = combined

    if parsed_cfgs != None:
        parsed_cfgs[cfgfile] = fin
    return(fin)


def get_cfg_option_bool(yobj, key, default=False):
    if key not in yobj:
        return default
    val = yobj[key]
    if val is True:
        return True
    if str(val).lower() in ['true', '1', 'on', 'yes']:
        return True
    return False


def get_cfg_option_str(yobj, key, default=None):
    if key not in yobj:
        return default
    return yobj[key]


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
    return(cur)


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
    return src


def delete_dir_contents(dirname):
    """
    Deletes all contents of a directory without deleting the directory itself.

    @param dirname: The directory whose contents should be deleted.
    """
    for node in os.listdir(dirname):
        node_fullpath = os.path.join(dirname, node)
        if os.path.isdir(node_fullpath):
            shutil.rmtree(node_fullpath)
        else:
            os.unlink(node_fullpath)


def write_file(filename, content, mode=0644, omode="wb"):
    """
    Writes a file with the given content and sets the file mode as specified.
    Resotres the SELinux context if possible.

    @param filename: The full path of the file to write.
    @param content: The content to write to the file.
    @param mode: The filesystem mode to set on the file.
    @param omode: The open mode used when opening the file (r, rb, a, etc.)
    """
    try:
        os.makedirs(os.path.dirname(filename))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise e

    f = open(filename, omode)
    if mode is not None:
        os.chmod(filename, mode)
    f.write(content)
    f.close()
    restorecon_if_possible(filename)


def restorecon_if_possible(path, recursive=False):
    if HAVE_LIBSELINUX and selinux.is_selinux_enabled():
        selinux.restorecon(path, recursive=recursive)


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
    return(subp(args)[0])


def runparts(dirp, skip_no_exist=True):
    if skip_no_exist and not os.path.isdir(dirp):
        return

    failed = 0
    for exe_name in sorted(os.listdir(dirp)):
        exe_path = os.path.join(dirp, exe_name)
        if os.path.isfile(exe_path) and os.access(exe_path, os.X_OK):
            popen = subprocess.Popen([exe_path])
            popen.communicate()
            if popen.returncode is not 0:
                failed += 1
                sys.stderr.write("failed: %s [%i]\n" %
                    (exe_path, popen.returncode))
    if failed:
        raise RuntimeError('runparts: %i failures' % failed)


def subp(args, input_=None):
    sp = subprocess.Popen(args, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    out, err = sp.communicate(input_)
    if sp.returncode is not 0:
        raise subprocess.CalledProcessError(sp.returncode, args, (out, err))
    return(out, err)


def render_to_file(template, outfile, searchList):
    t = Template(file='/etc/cloud/templates/%s.tmpl' % template,
                 searchList=[searchList])
    f = open(outfile, 'w')
    f.write(t.respond())
    f.close()


def render_string(template, searchList):
    return(Template(template, searchList=[searchList]).respond())


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
    except OSError, e:
        if e.errno == errno.ENOENT:
            return False
        raise


# raise OSError with enoent if not found
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

    no_exc = object()
    raise_err = no_exc
    for attempt in range(0, retries + 1):
        try:
            md_str = readurl(md_url, timeout=timeout)
            ud = readurl(ud_url, timeout=timeout)
            md = yaml.load(md_str)

            return(md, ud)
        except urllib2.HTTPError as e:
            raise_err = e
        except urllib2.URLError as e:
            raise_err = e
            if (isinstance(e.reason, OSError) and
                e.reason.errno == errno.ENOENT):
                raise_err = e.reason

        if attempt == retries:
            break

        #print "%s failed, sleeping" % attempt
        time.sleep(1)

    raise(raise_err)


def logexc(log, lvl=logging.DEBUG):
    log.log(lvl, traceback.format_exc())


class RecursiveInclude(Exception):
    pass


def read_file_with_includes(fname, rel=".", stack=None, patt=None):
    if stack is None:
        stack = []
    if not fname.startswith("/"):
        fname = os.sep.join((rel, fname))

    fname = os.path.realpath(fname)

    if fname in stack:
        raise(RecursiveInclude("%s recursively included" % fname))
    if len(stack) > 10:
        raise(RecursiveInclude("%s included, stack size = %i" %
                               (fname, len(stack))))

    if patt == None:
        patt = re.compile("^#(opt_include|include)[ \t].*$", re.MULTILINE)

    try:
        fp = open(fname)
        contents = fp.read()
        fp.close()
    except:
        raise

    rel = os.path.dirname(fname)
    stack.append(fname)

    cur = 0
    while True:
        match = patt.search(contents[cur:])
        if not match:
            break
        loc = match.start() + cur
        endl = match.end() + cur

        (key, cur_fname) = contents[loc:endl].split(None, 2)
        cur_fname = cur_fname.strip()

        try:
            inc_contents = read_file_with_includes(cur_fname, rel, stack, patt)
        except IOError, e:
            if e.errno == errno.ENOENT and key == "#opt_include":
                inc_contents = ""
            else:
                raise
        contents = contents[0:loc] + inc_contents + contents[endl + 1:]
        cur = loc + len(inc_contents)
    stack.pop()
    return(contents)


def read_conf_d(confd):
    # get reverse sorted list (later trumps newer)
    confs = sorted(os.listdir(confd), reverse=True)

    # remove anything not ending in '.cfg'
    confs = [f for f in confs if f.endswith(".cfg")]

    # remove anything not a file
    confs = [f for f in confs if os.path.isfile("%s/%s" % (confd, f))]

    cfg = {}
    for conf in confs:
        cfg = mergedict(cfg, read_conf("%s/%s" % (confd, conf)))

    return(cfg)


def read_conf_with_confd(cfgfile):
    cfg = read_conf(cfgfile)
    confd = False
    if "conf_d" in cfg:
        if cfg['conf_d'] is not None:
            confd = cfg['conf_d']
            if not isinstance(confd, str):
                raise Exception("cfgfile %s contains 'conf_d' "
                                "with non-string" % cfgfile)
    elif os.path.isdir("%s.d" % cfgfile):
        confd = "%s.d" % cfgfile

    if not confd:
        return(cfg)

    confd_cfg = read_conf_d(confd)

    return(mergedict(confd_cfg, cfg))


def get_cmdline():
    if 'DEBUG_PROC_CMDLINE' in os.environ:
        cmdline = os.environ["DEBUG_PROC_CMDLINE"]
    else:
        try:
            cmdfp = open("/proc/cmdline")
            cmdline = cmdfp.read().strip()
            cmdfp.close()
        except:
            cmdline = ""
    return(cmdline)


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

    return('\n'.join(tokens))


def ensure_dirs(dirlist, mode=0755):
    fixmodes = []
    for d in dirlist:
        try:
            if mode != None:
                os.makedirs(d)
            else:
                os.makedirs(d, mode)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            if mode != None:
                fixmodes.append(d)

    for d in fixmodes:
        os.chmod(d, mode)


def chownbyname(fname, user=None, group=None):
    uid = -1
    gid = -1
    if user == None and group == None:
        return
    if user:
        import pwd
        uid = pwd.getpwnam(user).pw_uid
    if group:
        import grp
        gid = grp.getgrnam(group).gr_gid

    os.chown(fname, uid, gid)


def readurl(url, data=None, timeout=None):
    openargs = {}
    if timeout != None:
        openargs['timeout'] = timeout

    if data is None:
        req = urllib2.Request(url)
    else:
        encoded = urllib.urlencode(data)
        req = urllib2.Request(url, encoded)

    response = urllib2.urlopen(req, **openargs)
    return(response.read())


# shellify, takes a list of commands
#  for each entry in the list
#    if it is an array, shell protect it (with single ticks)
#    if it is a string, do nothing
def shellify(cmdlist):
    content = "#!/bin/sh\n"
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


def dos2unix(string):
    # find first end of line
    pos = string.find('\n')
    if pos <= 0 or string[pos - 1] != '\r':
        return(string)
    return(string.replace('\r\n', '\n'))


def is_container():
    # is this code running in a container of some sort

    for helper in ('running-in-container', 'lxc-is-container'):
        try:
            # try to run a helper program. if it returns true
            # then we're inside a container. otherwise, no
            sp = subprocess.Popen(helper, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
            sp.communicate(None)
            return(sp.returncode == 0)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

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
        if e.errno != errno.ENOENT:
            pass

    # Detect OpenVZ containers
    if os.path.isdir("/proc/vz") and not os.path.isdir("/proc/bc"):
        return True

    try:
        # Detect Vserver containers
        with open("/proc/self/status") as fp:
            lines = fp.read().splitlines()
            for line in lines:
                if line.startswith("VxID:"):
                    (_key, val) = line.strip().split(":", 1)
                    if val != "0":
                        return True
    except IOError as e:
        if e.errno != errno.ENOENT:
            pass

    return False


def get_proc_env(pid):
    # return the environment in a dict that a given process id was started with
    env = {}
    with open("/proc/%s/environ" % pid) as fp:
        toks = fp.read().split("\0")
        for tok in toks:
            if tok == "":
                continue
            (name, val) = tok.split("=", 1)
            env[name] = val
    return env


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
    return(hostname, fqdn)


def get_fqdn_from_hosts(hostname, filename="/etc/hosts"):
    # this parses /etc/hosts to get a fqdn.  It should return the same
    # result as 'hostname -f <hostname>' if /etc/hosts.conf
    # did not have did not have 'bind' in the order attribute
    fqdn = None
    try:
        with open(filename, "r") as hfp:
            for line in hfp.readlines():
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
            hfp.close()
    except IOError as e:
        if e.errno == errno.ENOENT:
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
    return(is_resolvable(urlparse.urlparse(url).hostname))


def search_for_mirror(candidates):
    """ Search through a list of mirror urls for one that works """
    for cand in candidates:
        try:
            if is_resolvable_url(cand):
                return cand
        except Exception:
            raise

    return None


def close_stdin():
    """
    reopen stdin as /dev/null so even subprocesses or other os level things get
    /dev/null as input.

    if _CLOUD_INIT_SAVE_STDIN is set in environment to a non empty or '0' value
    then input will not be closed (only useful potentially for debugging).
    """
    if os.environ.get("_CLOUD_INIT_SAVE_STDIN") in ("", "0", False):
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
    except subprocess.CalledProcessError:
        return([])
    return(str(out).splitlines())


class mountFailedError(Exception):
    pass


def mount_callback_umount(device, callback, data=None):
    """
    mount the device, call method 'callback' passing the directory
    in which it was mounted, then unmount.  Return whatever 'callback'
    returned.  If data != None, also pass data to callback.
    """

    def _cleanup(umount, tmpd):
        if umount:
            try:
                subp(["umount", '-l', umount])
            except subprocess.CalledProcessError:
                raise
        if tmpd:
            os.rmdir(tmpd)

    # go through mounts to see if it was already mounted
    fp = open("/proc/mounts")
    mounts = fp.readlines()
    fp.close()

    tmpd = None

    mounted = {}
    for mpline in mounts:
        (dev, mp, fstype, _opts, _freq, _passno) = mpline.split()
        mp = mp.replace("\\040", " ")
        mounted[dev] = (dev, fstype, mp, False)

    umount = False
    if device in mounted:
        mountpoint = "%s/" % mounted[device][2]
    else:
        tmpd = tempfile.mkdtemp()

        mountcmd = ["mount", "-o", "ro", device, tmpd]

        try:
            (_out, _err) = subp(mountcmd)
            umount = tmpd
        except subprocess.CalledProcessError as exc:
            _cleanup(umount, tmpd)
            raise mountFailedError(exc.output[1])

        mountpoint = "%s/" % tmpd

    try:
        if data == None:
            ret = callback(mountpoint)
        else:
            ret = callback(mountpoint, data)

    except Exception as exc:
        _cleanup(umount, tmpd)
        raise exc

    _cleanup(umount, tmpd)

    return(ret)


def wait_for_url(urls, max_wait=None, timeout=None,
                 status_cb=None, headers_cb=None):
    """
    urls:      a list of urls to try
    max_wait:  roughly the maximum time to wait before giving up
               The max time is *actually* len(urls)*timeout as each url will
               be tried once and given the timeout provided.
    timeout:   the timeout provided to urllib2.urlopen
    status_cb: call method with string message when a url is not available
    headers_cb: call method with single argument of url to get headers
                for request.

    the idea of this routine is to wait for the EC2 metdata service to
    come up.  On both Eucalyptus and EC2 we have seen the case where
    the instance hit the MD before the MD service was up.  EC2 seems
    to have permenantely fixed this, though.

    In openstack, the metadata service might be painfully slow, and
    unable to avoid hitting a timeout of even up to 10 seconds or more
    (LP: #894279) for a simple GET.

    Offset those needs with the need to not hang forever (and block boot)
    on a system where cloud-init is configured to look for EC2 Metadata
    service but is not going to find one.  It is possible that the instance
    data host (169.254.169.254) may be firewalled off Entirely for a sytem,
    meaning that the connection will block forever unless a timeout is set.
    """
    starttime = time.time()

    sleeptime = 1

    def nullstatus_cb(msg):
        return

    if status_cb == None:
        status_cb = nullstatus_cb

    def timeup(max_wait, starttime):
        return((max_wait <= 0 or max_wait == None) or
               (time.time() - starttime > max_wait))

    loop_n = 0
    while True:
        sleeptime = int(loop_n / 5) + 1
        for url in urls:
            now = time.time()
            if loop_n != 0:
                if timeup(max_wait, starttime):
                    break
                if timeout and (now + timeout > (starttime + max_wait)):
                    # shorten timeout to not run way over max_time
                    timeout = int((starttime + max_wait) - now)

            reason = ""
            try:
                if headers_cb != None:
                    headers = headers_cb(url)
                else:
                    headers = {}

                req = urllib2.Request(url, data=None, headers=headers)
                resp = urllib2.urlopen(req, timeout=timeout)
                if resp.read() != "":
                    return url
                reason = "empty data [%s]" % resp.getcode()
            except urllib2.HTTPError as e:
                reason = "http error [%s]" % e.code
            except urllib2.URLError as e:
                reason = "url error [%s]" % e.reason
            except socket.timeout as e:
                reason = "socket timeout [%s]" % e
            except Exception as e:
                reason = "unexpected error [%s]" % e

            status_cb("'%s' failed [%s/%ss]: %s" %
                      (url, int(time.time() - starttime), max_wait,
                       reason))

        if timeup(max_wait, starttime):
            break

        loop_n = loop_n + 1
        time.sleep(sleeptime)

    return False


def keyval_str_to_dict(kvstring):
    ret = {}
    for tok in kvstring.split():
        try:
            (key, val) = tok.split("=", 1)
        except ValueError:
            key = tok
            val = True
        ret[key] = val

    return(ret)
