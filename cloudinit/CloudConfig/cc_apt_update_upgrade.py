# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

def handle(name,cfg,cloud,log,args):
    update = util.get_cfg_option_bool(cfg, 'apt_update', False)
    upgrade = util.get_cfg_option_bool(cfg, 'apt_upgrade', False)

    if not util.get_cfg_option_bool(cfg, \
        'apt_preserve_sources_list', False):
        if cfg.has_key("apt_mirror"):
            mirror = cfg["apt_mirror"]
        else:
            mirror = cloud.get_mirror()
        generate_sources_list(mirror)
        old_mir = util.get_cfg_option_str(cfg,'apt_old_mirror', \
            "archive.ubuntu.com/ubuntu")
        rename_apt_lists(old_mir, mirror)

    # process 'apt_sources'
    if cfg.has_key('apt_sources'):
        errors = add_sources(cfg['apt_sources'])
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

    pkglist = []
    if 'packages' in cfg:
        if isinstance(cfg['packages'],list):
            pkglist = cfg['packages']
        else: pkglist.append(cfg['packages'])

    if update or upgrade or pkglist:
        #retcode = subprocess.call(list)
        subprocess.Popen(['apt-get', 'update']).communicate()

    e=os.environ.copy()
    e['DEBIAN_FRONTEND']='noninteractive'

    if upgrade:
        cmd=[ 'apt-get', '--option', 'Dpkg::Options::=--force-confold',
              'upgrade', '--assume-yes' ]

        subprocess.Popen(cmd, env=e).communicate()

    if pkglist:
        cmd=['apt-get', 'install', '--assume-yes']
        cmd.extend(pkglist)
        subprocess.Popen(cmd, env=e).communicate()

    return(True)

def mirror2lists_fileprefix(mirror):
    file=mirror
    # take of http:// or ftp://
    if file.endswith("/"): file=file[0:-1]
    pos=file.find("://")
    if pos >= 0:
        file=file[pos+3:]
    file=file.replace("/","_")
    return file

def rename_apt_lists(omirror,new_mirror,lists_d="/var/lib/apt/lists"):
    
    oprefix="%s/%s" % (lists_d,mirror2lists_fileprefix(omirror))
    nprefix="%s/%s" % (lists_d,mirror2lists_fileprefix(new_mirror))
    if(oprefix==nprefix): return
    olen=len(oprefix)
    for file in glob.glob("%s_*" % oprefix):
        os.rename(file,"%s%s" % (nprefix, file[olen:]))

def generate_sources_list(mirror):
    stdout, stderr = subprocess.Popen(['lsb_release', '-cs'], stdout=subprocess.PIPE).communicate()
    codename = stdout.strip()

    util.render_to_file('sources.list', '/etc/apt/sources.list', \
        { 'mirror' : mirror, 'codename' : codename })

# srclist is a list of dictionaries, 
# each entry must have: 'source'
# may have: key, ( keyid and keyserver)
def add_sources(srclist):
    elst = []

    for ent in srclist:
        if not ent.has_key('source'):
            elst.append([ "", "missing source" ])
            continue

        source=ent['source']
        if source.startswith("ppa:"):
            try: util.subp(["add-apt-repository",source])
            except:
                elst.append([source, "add-apt-repository failed"])
            continue

        if not ent.has_key('filename'):
            ent['filename']='cloud_config_sources.list'

        if not ent['filename'].startswith("/"):
            ent['filename'] = "%s/%s" % \
                ("/etc/apt/sources.list.d/", ent['filename'])

        if ( ent.has_key('keyid') and not ent.has_key('key') ):
            ks = "keyserver.ubuntu.com"
            if ent.has_key('keyserver'): ks = ent['keyserver']
            try:
                ent['key'] = util.getkeybyid(ent['keyid'], ks)
            except:
                elst.append([source,"failed to get key from %s" % ks])
                continue

        if ent.has_key('key'):
            try: util.subp(('apt-key', 'add', '-'), ent['key'])
            except:
                elst.append([source, "failed add key"])

        try: util.write_file(ent['filename'], source + "\n", omode="ab")
        except:
            elst.append([source, "failed write to file %s" % ent['filename']])

    return(elst)


