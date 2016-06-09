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

import glob
import os
import re

from cloudinit import templater
from cloudinit import util
from cloudinit import gpg

distros = ['ubuntu', 'debian']

PROXY_TPL = "Acquire::HTTP::Proxy \"%s\";\n"
APT_CONFIG_FN = "/etc/apt/apt.conf.d/94cloud-init-config"
APT_PROXY_FN = "/etc/apt/apt.conf.d/95cloud-init-proxy"

# this will match 'XXX:YYY' (ie, 'cloud-archive:foo' or 'ppa:bar')
ADD_APT_REPO_MATCH = r"^[\w-]+:\w"


def handle(name, cfg, cloud, log, _args):
    if util.is_false(cfg.get('apt_configure_enabled', True)):
        log.debug("Skipping module named %s, disabled by config.", name)
        return

    release = get_release()
    mirrors = find_apt_mirror_info(cloud, cfg)
    if not mirrors or "primary" not in mirrors:
        log.debug(("Skipping module named %s,"
                   " no package 'mirror' located"), name)
        return

    # backwards compatibility
    mirror = mirrors["primary"]
    mirrors["mirror"] = mirror

    log.debug("Mirror info: %s" % mirrors)

    if not util.get_cfg_option_bool(cfg,
                                    'apt_preserve_sources_list', False):
        generate_sources_list(cfg, release, mirrors, cloud, log)
        old_mirrors = cfg.get('apt_old_mirrors',
                              {"primary": "archive.ubuntu.com/ubuntu",
                               "security": "security.ubuntu.com/ubuntu"})
        rename_apt_lists(old_mirrors, mirrors)

    try:
        apply_apt_config(cfg, APT_PROXY_FN, APT_CONFIG_FN)
    except Exception as e:
        log.warn("failed to proxy or apt config info: %s", e)

    # Process 'apt_sources'
    if 'apt_sources' in cfg:
        params = mirrors
        params['RELEASE'] = release
        params['MIRROR'] = mirror

        matchcfg = cfg.get('add_apt_repo_match', ADD_APT_REPO_MATCH)
        if matchcfg:
            matcher = re.compile(matchcfg).search
        else:
            def matcher(x):
                return False

        errors = add_apt_sources(cfg['apt_sources'], params,
                                 aa_repo_match=matcher)
        for e in errors:
            log.warn("Add source error: %s", ':'.join(e))

    dconf_sel = util.get_cfg_option_str(cfg, 'debconf_selections', False)
    if dconf_sel:
        log.debug("Setting debconf selections per cloud config")
        try:
            util.subp(('debconf-set-selections', '-'), dconf_sel)
        except Exception:
            util.logexc(log, "Failed to run debconf-set-selections")


def mirrorurl_to_apt_fileprefix(mirror):
    string = mirror
    # take off http:// or ftp://
    if string.endswith("/"):
        string = string[0:-1]
    pos = string.find("://")
    if pos >= 0:
        string = string[pos + 3:]
    string = string.replace("/", "_")
    return string


def rename_apt_lists(old_mirrors, new_mirrors, lists_d="/var/lib/apt/lists"):
    for (name, omirror) in old_mirrors.items():
        nmirror = new_mirrors.get(name)
        if not nmirror:
            continue
        oprefix = os.path.join(lists_d, mirrorurl_to_apt_fileprefix(omirror))
        nprefix = os.path.join(lists_d, mirrorurl_to_apt_fileprefix(nmirror))
        if oprefix == nprefix:
            continue
        olen = len(oprefix)
        for filename in glob.glob("%s_*" % oprefix):
            util.rename(filename, "%s%s" % (nprefix, filename[olen:]))


def get_release():
    (stdout, _stderr) = util.subp(['lsb_release', '-cs'])
    return stdout.strip()


def generate_sources_list(cfg, codename, mirrors, cloud, log):
    params = {'codename': codename}
    for k in mirrors:
        params[k] = mirrors[k]

    custtmpl = cfg.get('apt_custom_sources_list', None)
    if custtmpl is not None:
        templater.render_string_to_file(custtmpl,
                                        '/etc/apt/sources.list', params)
        return

    template_fn = cloud.get_template_filename('sources.list.%s' %
                                              (cloud.distro.name))
    if not template_fn:
        template_fn = cloud.get_template_filename('sources.list')
        if not template_fn:
            log.warn("No template found, not rendering /etc/apt/sources.list")
            return

    templater.render_to_file(template_fn, '/etc/apt/sources.list', params)


def add_apt_key_raw(key):
    """
    actual adding of a key as defined in key argument
    to the system
    """
    try:
        util.subp(('apt-key', 'add', '-'), key)
    except util.ProcessExecutionError:
        raise ValueError('failed to add apt GPG Key to apt keyring')


def add_apt_key(ent):
    """
    add key to the system as defined in ent (if any)
    supports raw keys or keyid's
    The latter will as a first step fetch the raw key from a keyserver
    """
    if 'keyid' in ent and 'key' not in ent:
        keyserver = "keyserver.ubuntu.com"
        if 'keyserver' in ent:
            keyserver = ent['keyserver']
        ent['key'] = gpg.gpg_getkeybyid(ent['keyid'], keyserver)

    if 'key' in ent:
        add_apt_key_raw(ent['key'])


def convert_to_new_format(srclist):
    """convert_to_new_format
       convert the old list based format to the new dict based one
    """
    srcdict = {}
    if isinstance(srclist, list):
        for srcent in srclist:
            if 'filename' not in srcent:
                # file collides for multiple !filename cases for compatibility
                # yet we need them all processed, so not same dictionary key
                srcent['filename'] = "cloud_config_sources.list"
                key = util.rand_dict_key(srcdict, "cloud_config_sources.list")
            else:
                # all with filename use that as key (matching new format)
                key = srcent['filename']
            srcdict[key] = srcent
    elif isinstance(srclist, dict):
        srcdict = srclist
    else:
        raise ValueError("unknown apt_sources format")

    return srcdict


def add_apt_sources(srclist, template_params=None, aa_repo_match=None):
    """
    add entries in /etc/apt/sources.list.d for each abbreviated
    sources.list entry in 'srclist'.  When rendering template, also
    include the values in dictionary searchList
    """
    if template_params is None:
        template_params = {}

    if aa_repo_match is None:
        def aa_repo_match(x):
            return False

    errorlist = []
    srcdict = convert_to_new_format(srclist)

    for filename in srcdict:
        ent = srcdict[filename]
        if 'filename' not in ent:
            ent['filename'] = filename

        # keys can be added without specifying a source
        try:
            add_apt_key(ent)
        except ValueError as detail:
            errorlist.append([ent, detail])

        if 'source' not in ent:
            errorlist.append(["", "missing source"])
            continue
        source = ent['source']
        source = templater.render_string(source, template_params)

        if not ent['filename'].startswith(os.path.sep):
            ent['filename'] = os.path.join("/etc/apt/sources.list.d/",
                                           ent['filename'])

        if aa_repo_match(source):
            try:
                util.subp(["add-apt-repository", source])
            except util.ProcessExecutionError as e:
                errorlist.append([source,
                                  ("add-apt-repository failed. " + str(e))])
            continue

        try:
            contents = "%s\n" % (source)
            util.write_file(ent['filename'], contents, omode="ab")
        except Exception:
            errorlist.append([source,
                             "failed write to file %s" % ent['filename']])

    return errorlist


def find_apt_mirror_info(cloud, cfg):
    """find an apt_mirror given the cloud and cfg provided."""

    mirror = None

    # this is less preferred way of specifying mirror preferred would be to
    # use the distro's search or package_mirror.
    mirror = cfg.get("apt_mirror", None)

    search = cfg.get("apt_mirror_search", None)
    if not mirror and search:
        mirror = util.search_for_mirror(search)

    if (not mirror and
            util.get_cfg_option_bool(cfg, "apt_mirror_search_dns", False)):
        mydom = ""
        doms = []

        # if we have a fqdn, then search its domain portion first
        (_hostname, fqdn) = util.get_hostname_fqdn(cfg, cloud)
        mydom = ".".join(fqdn.split(".")[1:])
        if mydom:
            doms.append(".%s" % mydom)

        doms.extend((".localdomain", "",))

        mirror_list = []
        distro = cloud.distro.name
        mirrorfmt = "http://%s-mirror%s/%s" % (distro, "%s", distro)
        for post in doms:
            mirror_list.append(mirrorfmt % (post))

        mirror = util.search_for_mirror(mirror_list)

    mirror_info = cloud.datasource.get_package_mirror_info()

    # this is a bit strange.
    # if mirror is set, then one of the legacy options above set it
    # but they do not cover security. so we need to get that from
    # get_package_mirror_info
    if mirror:
        mirror_info.update({'primary': mirror})

    return mirror_info


def apply_apt_config(cfg, proxy_fname, config_fname):
    # Set up any apt proxy
    cfgs = (('apt_proxy', 'Acquire::HTTP::Proxy "%s";'),
            ('apt_http_proxy', 'Acquire::HTTP::Proxy "%s";'),
            ('apt_ftp_proxy', 'Acquire::FTP::Proxy "%s";'),
            ('apt_https_proxy', 'Acquire::HTTPS::Proxy "%s";'))

    proxies = [fmt % cfg.get(name) for (name, fmt) in cfgs if cfg.get(name)]
    if len(proxies):
        util.write_file(proxy_fname, '\n'.join(proxies) + '\n')
    elif os.path.isfile(proxy_fname):
        util.del_file(proxy_fname)

    if cfg.get('apt_config', None):
        util.write_file(config_fname, cfg.get('apt_config'))
    elif os.path.isfile(config_fname):
        util.del_file(config_fname)
