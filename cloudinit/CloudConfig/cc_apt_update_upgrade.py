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

import cloudinit.util as util
import subprocess
import traceback
import os
import glob
import cloudinit.CloudConfig as cc


def handle(_name, cfg, cloud, log, _args):
    update = util.get_cfg_option_bool(cfg, 'apt_update', False)
    upgrade = util.get_cfg_option_bool(cfg, 'apt_upgrade', False)

    release = get_release()

    mirror = find_apt_mirror(cloud, cfg)

    log.debug("selected mirror at: %s" % mirror)

    if not util.get_cfg_option_bool(cfg, \
        'apt_preserve_sources_list', False):
        generate_sources_list(release, mirror)
        old_mir = util.get_cfg_option_str(cfg, 'apt_old_mirror', \
            "archive.ubuntu.com/ubuntu")
        rename_apt_lists(old_mir, mirror)

    # set up proxy
    proxy = cfg.get("apt_proxy", None)
    proxy_filename = "/etc/apt/apt.conf.d/95cloud-init-proxy"
    if proxy:
        try:
            contents = "Acquire::HTTP::Proxy \"%s\";\n"
            with open(proxy_filename, "w") as fp:
                fp.write(contents % proxy)
        except Exception as e:
            log.warn("Failed to write proxy to %s" % proxy_filename)
    elif os.path.isfile(proxy_filename):
        os.unlink(proxy_filename)

    # process 'apt_sources'
    if 'apt_sources' in cfg:
        errors = add_sources(cfg['apt_sources'],
                             {'MIRROR': mirror, 'RELEASE': release})
        for e in errors:
            log.warn("Source Error: %s\n" % ':'.join(e))

    dconf_sel = util.get_cfg_option_str(cfg, 'debconf_selections', False)
    if dconf_sel:
        log.debug("setting debconf selections per cloud config")
        try:
            util.subp(('debconf-set-selections', '-'), dconf_sel)
        except:
            log.error("Failed to run debconf-set-selections")
            log.debug(traceback.format_exc())

    pkglist = util.get_cfg_option_list_or_str(cfg, 'packages', [])

    errors = []
    if update or len(pkglist) or upgrade:
        try:
            cc.update_package_sources()
        except subprocess.CalledProcessError as e:
            log.warn("apt-get update failed")
            log.debug(traceback.format_exc())
            errors.append(e)

    if upgrade:
        try:
            cc.apt_get("upgrade")
        except subprocess.CalledProcessError as e:
            log.warn("apt upgrade failed")
            log.debug(traceback.format_exc())
            errors.append(e)

    if len(pkglist):
        try:
            cc.install_packages(pkglist)
        except subprocess.CalledProcessError as e:
            log.warn("Failed to install packages: %s " % pkglist)
            log.debug(traceback.format_exc())
            errors.append(e)

    if len(errors):
        raise errors[0]

    return(True)


def mirror2lists_fileprefix(mirror):
    string = mirror
    # take of http:// or ftp://
    if string.endswith("/"):
        string = string[0:-1]
    pos = string.find("://")
    if pos >= 0:
        string = string[pos + 3:]
    string = string.replace("/", "_")
    return string


def rename_apt_lists(omirror, new_mirror, lists_d="/var/lib/apt/lists"):
    oprefix = "%s/%s" % (lists_d, mirror2lists_fileprefix(omirror))
    nprefix = "%s/%s" % (lists_d, mirror2lists_fileprefix(new_mirror))
    if(oprefix == nprefix):
        return
    olen = len(oprefix)
    for filename in glob.glob("%s_*" % oprefix):
        os.rename(filename, "%s%s" % (nprefix, filename[olen:]))


def get_release():
    stdout, _stderr = subprocess.Popen(['lsb_release', '-cs'],
                                       stdout=subprocess.PIPE).communicate()
    return(str(stdout).strip())


def generate_sources_list(codename, mirror):
    util.render_to_file('sources.list', '/etc/apt/sources.list', \
        {'mirror': mirror, 'codename': codename})


def add_sources(srclist, searchList=None):
    """
    add entries in /etc/apt/sources.list.d for each abbreviated
    sources.list entry in 'srclist'.  When rendering template, also
    include the values in dictionary searchList
    """
    if searchList is None:
        searchList = {}
    elst = []

    for ent in srclist:
        if 'source' not in ent:
            elst.append(["", "missing source"])
            continue

        source = ent['source']
        if source.startswith("ppa:"):
            try:
                util.subp(["add-apt-repository", source])
            except:
                elst.append([source, "add-apt-repository failed"])
            continue

        source = util.render_string(source, searchList)

        if 'filename' not in ent:
            ent['filename'] = 'cloud_config_sources.list'

        if not ent['filename'].startswith("/"):
            ent['filename'] = "%s/%s" % \
                ("/etc/apt/sources.list.d/", ent['filename'])

        if ('keyid' in ent and 'key' not in ent):
            ks = "keyserver.ubuntu.com"
            if 'keyserver' in ent:
                ks = ent['keyserver']
            try:
                ent['key'] = util.getkeybyid(ent['keyid'], ks)
            except:
                elst.append([source, "failed to get key from %s" % ks])
                continue

        if 'key' in ent:
            try:
                util.subp(('apt-key', 'add', '-'), ent['key'])
            except:
                elst.append([source, "failed add key"])

        try:
            util.write_file(ent['filename'], source + "\n", omode="ab")
        except:
            elst.append([source, "failed write to file %s" % ent['filename']])

    return(elst)


def find_apt_mirror(cloud, cfg):
    """ find an apt_mirror given the cloud and cfg provided """

    # TODO: distro and defaults should be configurable
    distro = "ubuntu"
    defaults = {
        'ubuntu': "http://archive.ubuntu.com/ubuntu",
        'debian': "http://archive.debian.org/debian",
    }
    mirror = None

    cfg_mirror = cfg.get("apt_mirror", None)
    if cfg_mirror:
        mirror = cfg["apt_mirror"]
    elif "apt_mirror_search" in cfg:
        mirror = util.search_for_mirror(cfg['apt_mirror_search'])
    else:
        if cloud:
            mirror = cloud.get_mirror()

        mydom = ""

        doms = []

        if not mirror and cloud:
            # if we have a fqdn, then search its domain portion first
            (_hostname, fqdn) = util.get_hostname_fqdn(cfg, cloud)
            mydom = ".".join(fqdn.split(".")[1:])
            if mydom:
                doms.append(".%s" % mydom)

        if not mirror:
            doms.extend((".localdomain", "",))

            mirror_list = []
            mirrorfmt = "http://%s-mirror%s/%s" % (distro, "%s", distro)
            for post in doms:
                mirror_list.append(mirrorfmt % post)

            mirror = util.search_for_mirror(mirror_list)

    if not mirror:
        mirror = defaults[distro]

    return mirror
