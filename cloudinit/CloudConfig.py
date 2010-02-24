#
#    Copyright (C) 2008-2010 Canonical Ltd.
#
#    Author: Chuck Short <chuck.short@canonical.com>
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
#
import yaml
import re
import cloudinit
import cloudinit.util as util
import pwd
import socket
import subprocess
import os
import glob
import sys
import time

per_instance="once-per-instance"
cronpre = "/etc/cron.d/cloudinit"

class CloudConfig():
    cfgfile = None
    handlers = { }
    cfg = None

    def __init__(self,cfgfile):
        self.cloud = cloudinit.CloudInit()
        self.cfg = self.get_config_obj(cfgfile)
        self.cloud.get_data_source()
        self.add_handler('apt-update-upgrade', self.h_apt_update_upgrade)
        self.add_handler('config-ssh')
        self.add_handler('disable-ec2-metadata',
            self.h_disable_ec2_metadata, "always")
        self.add_handler('config-mounts')
        self.add_handler('config-puppet')
        self.add_handler('config-misc')

    def get_config_obj(self,cfgfile):
        f=file(cfgfile)
        cfg=yaml.load(f.read())
        f.close()
        if cfg is None: cfg = { }
        return(util.mergedict(cfg,self.cloud.cfg))

    def convert_old_config(self):
        # support reading the old ConfigObj format file and turning it
        # into a yaml string
        try:
            f = file(self.conffile)
            str=file.read().replace('=',': ')
            f.close()
            return str
        except:
            return("")

    def add_handler(self, name, handler=None, freq=None):
        if handler is None:
            try:
                handler=getattr(self,'h_%s' % name.replace('-','_'))
            except:
                raise Exception("Unknown hander for name %s" %name)
        if freq is None:
            freq = per_instance

        self.handlers[name]= { 'handler': handler, 'freq': freq }

    def get_handler_info(self, name):
        return(self.handlers[name]['handler'], self.handlers[name]['freq'])

	def parse_ssh_keys(self):
		disableRoot = self.cfg['disable_root']
		if disableRoot == 'true':
			value = 'disabled_root'
			return value
		else:
			ec2Key = self.cfg['ec2_fetch_key']
			if ec2Key != 'none':
				value = 'default_key'
				return value
			else:
				return ec2Key

    def handle(self, name, args):
        handler = None
        freq = None
        try:
            (handler, freq) = self.get_handler_info(name)
        except:
            raise Exception("Unknown config key %s\n" % name)

        self.cloud.sem_and_run(name, freq, handler, [ name, args ])

    def h_apt_update_upgrade(self,name,args):
        update = util.get_cfg_option_bool(self.cfg, 'apt_update', False)
        upgrade = util.get_cfg_option_bool(self.cfg, 'apt_upgrade', False)

        if not util.get_cfg_option_bool(self.cfg, \
            'apt_preserve_sources_list', False):
            if self.cfg.has_key("apt_mirror"):
                mirror = self.cfg["apt_mirror"]
            else:
                mirror = self.cloud.get_mirror()
            generate_sources_list(mirror)

        # process 'apt_sources'
        if self.cfg.has_key('apt_sources'):
            errors = add_sources(self.cfg['apt_sources'])
            for e in errors:
                warn("Source Error: %s\n" % ':'.join(e))

        pkglist = []
        if 'packages' in self.cfg:
            if isinstance(self.cfg['packages'],list):
                pkglist = self.cfg['packages']
            else: pkglist.append(self.cfg['packages'])

        if update or upgrade or pkglist:
            #retcode = subprocess.call(list)
		    subprocess.Popen(['apt-get', 'update']).communicate()

        e=os.environ.copy()
        e['DEBIAN_FRONTEND']='noninteractive'

        if upgrade:
            subprocess.Popen(['apt-get', 'upgrade', '--assume-yes'], env=e).communicate()

        if pkglist:
            cmd=['apt-get', 'install', '--assume-yes']
            cmd.extend(pkglist)
            subprocess.Popen(cmd, env=e).communicate()

        return(True)

    def h_disable_ec2_metadata(self,name,args):
        if util.get_cfg_option_bool(self.cfg, "disable_ec2_metadata", False):
            fwall="route add -host 169.254.169.254 reject"
            subprocess.call(fwall.split(' '))

    def h_config_ssh(self,name,args):
        # remove the static keys from the pristine image
        for f in glob.glob("/etc/ssh/ssh_host_*_key*"):
            try: os.unlink(f)
            except: pass

        if self.cfg.has_key("ssh_keys"):
            # if there are keys in cloud-config, use them
            key2file = {
                "rsa_private" : ("/etc/ssh/ssh_host_rsa_key", 0600),
                "rsa_public"  : ("/etc/ssh/ssh_host_rsa_key.pub", 0644),
                "dsa_private" : ("/etc/ssh/ssh_host_dsa_key", 0600),
                "dsa_public"  : ("/etc/ssh/ssh_host_dsa_key.pub", 0644)
            }

            for key,val in self.cfg["ssh_keys"].items():
                if key2file.has_key(key):
                    util.write_file(key2file[key][0],val,key2file[key][1])
        else:
            # if not, generate them
            genkeys ='ssh-keygen -f /etc/ssh/ssh_host_rsa_key -t rsa -N ""; '
            genkeys+='ssh-keygen -f /etc/ssh/ssh_host_dsa_key -t dsa -N ""; '
            subprocess.call(('sh', '-c', "{ %s } </dev/null" % (genkeys)))

        try:
            user = util.get_cfg_option_str(self.cfg,'user')
            disable_root = util.get_cfg_option_bool(self.cfg, "disable_root", True)
            keys = self.cloud.get_public_ssh_keys()

            if self.cfg.has_key("ssh_authorized_keys"):
                cfgkeys = self.cfg["ssh_authorized_keys"]
                keys.extend(cfgkeys)

            apply_credentials(keys,user,disable_root)
        except:
            warn("applying credentials failed!\n")

        send_ssh_keys_to_console()

    def h_config_misc(self,name,args):
        handle_updates_check(self.cfg)
        handle_runcmd(self.cfg)

    def h_config_puppet(self,name,args):
        # If there isn't a puppet key in the configuration don't do anything
        if not self.cfg.has_key('puppet'): return
        puppet_cfg = self.cfg['puppet']
        # Start by installing the puppet package ...
        e=os.environ.copy()
        e['DEBIAN_FRONTEND']='noninteractive'
        # Make sure that the apt database is updated since it's not run by
        # default
        # Note: we should have a helper to check if apt-get update 
        # has already been run on this instance to speed the boot time.
        subprocess.check_call(['apt-get', 'update'], env=e)
        subprocess.check_call(['apt-get', 'install', '--assume-yes',
                               'puppet'], env=e)
        # ... and then update the puppet configuration
        if puppet_cfg.has_key('conf'):
            # Add all sections from the conf object to puppet.conf
            puppet_conf_fh = open('/etc/puppet/puppet.conf', 'a')
            for cfg_name, cfg in puppet_cfg['conf'].iteritems():
                # ca_cert configuration is a special case
                # Dump the puppetmaster ca certificate in the correct place
                if cfg_name == 'ca_cert':
                    # Puppet ssl sub-directory isn't created yet
                    # Create it with the proper permissions and ownership
                    os.makedirs('/var/lib/puppet/ssl')
                    os.chmod('/var/lib/puppet/ssl', 0771)
                    os.chown('/var/lib/puppet/ssl',
                             pwd.getpwnam('puppet').pw_uid, 0)
                    os.makedirs('/var/lib/puppet/ssl/certs/')
                    os.chown('/var/lib/puppet/ssl/certs/',
                             pwd.getpwnam('puppet').pw_uid, 0)
                    ca_fh = open('/var/lib/puppet/ssl/certs/ca.pem', 'w')
                    ca_fh.write(cfg)
                    ca_fh.close()
                    os.chown('/var/lib/puppet/ssl/certs/ca.pem',
                             pwd.getpwnam('puppet').pw_uid, 0)
                else:
                    puppet_conf_fh.write("\n[%s]\n" % (cfg_name))
                    for o, v in cfg.iteritems():
                        if o == 'certname':
                            # Expand %f as the fqdn
                            v = v.replace("%f", socket.getfqdn())
                            # Expand %i as the instance id
                            v = v.replace("%i",
                                  self.cloud.datasource.get_instance_id())
                            # certname needs to be downcase
                            v = v.lower()
                        puppet_conf_fh.write("%s=\"%s\"\n" % (o, v))
            puppet_conf_fh.close()
        # Set puppet default file to automatically start
        subprocess.check_call(['sed', '-i',
                               '-e', 's/^START=.*/START=yes/',
                               '/etc/default/puppet'])
        # Start puppetd
        subprocess.check_call(['service', 'puppet', 'start'])

    def h_ec2_ebs_mounts(self,name,args):
        print "Warning, not doing anything for config %s" % name

    def h_config_setup_raid(self,name,args):
        print "Warning, not doing anything for config %s" % name

    def h_config_runurl(self,name,args):
        print "Warning, not doing anything for config %s" % name

    def h_config_mounts(self,name,args):
        # handle 'mounts'

        # these are our default set of mounts
        defmnts = [ [ "ephemeral0", "/mnt", "auto", "defaults", "0", "0" ],
                    [ "swap", "none", "swap", "sw", "0", "0" ] ]

        # fs_spec, fs_file, fs_vfstype, fs_mntops, fs-freq, fs_passno
        defvals = [ None, None, "auto", "defaults", "0", "0" ]

        cfgmnt = [ ]
        if self.cfg.has_key("mounts"):
            cfgmnt = self.cfg["mounts"]
    
        for i in range(len(cfgmnt)):
            # skip something that wasn't a list
            if not isinstance(cfgmnt[i],list): continue

            # workaround, allow user to specify 'ephemeral'
            # rather than more ec2 correct 'ephemeral0'
            if cfgmnt[i] == "ephemeral":
                cfgmnt[i] = "ephemeral0"

            newname = cfgmnt[i][0]
            if not newname.startswith("/"):
                newname = self.cloud.device_name_to_device(cfgmnt[i][0])
            if newname is not None:
                cfgmnt[i][0] = newname
            else:
                # there is no good way of differenciating between
                # a name that *couldn't* exist in the md service and
                # one that merely didnt
                # in order to allow user to specify 'sda3' rather
                # than '/dev/sda3', go through some hoops
                ok = False
                for f in [ "/", "sd", "hd", "vd", "xvd" ]:
                    if cfgmnt[i][0].startswith(f):
                        ok = True
                        break
                if not ok:
                    cfgmnt[i][1] = None
    
        for i in range(len(cfgmnt)):
            # fill in values with 
            for j in range(len(defvals)):
                if len(cfgmnt[i]) <= j:
                    cfgmnt[i].append(defvals[j])
                elif cfgmnt[i][j] is None:
                    cfgmnt[i][j] = defvals[j]
    
            if not cfgmnt[i][0].startswith("/"):
                cfgmnt[i][0]="/dev/%s" % cfgmnt[i][0]
    
            # if the second entry in the list is 'None' this
            # clears all previous entries of that same 'fs_spec'
            # (fs_spec is the first field in /etc/fstab, ie, that device)
            if cfgmnt[i][1] is None:
                for j in range(i):
                    if cfgmnt[j][0] == cfgmnt[i][0]:
                        cfgmnt[j][1] = None
    

        # for each of the "default" mounts, add them only if no other
        # entry has the same device name
        for defmnt in defmnts:
            devname = self.cloud.device_name_to_device(defmnt[0])
            if devname is None: continue
            if not devname.startswith("/"):
                defmnt[0] = "/dev/%s" % devname

            cfgmnt_has = False
            for cfgm in cfgmnt:
                if cfgm[0] == defmnt[0]:
                    cfgmnt_has = True
                    break
            
            if cfgmnt_has: continue
            cfgmnt.append(defmnt)

    
        # now, each entry in the cfgmnt list has all fstab values
        # if the second field is None (not the string, the value) we skip it
        actlist = filter(lambda x: x[1] is not None, cfgmnt)
    
        if len(actlist) == 0: return
    
        needswap = False
        dirs = [ ]

        fstab=file("/etc/fstab","ab")
        fstab.write("# cloud-config mounts\n")
        for line in actlist:
            fstab.write('\t'.join(line) + "\n")
            if line[2] == "swap": needswap = True
            if line[1].startswith("/"): dirs.append(line[1])
        fstab.close()
    
        if needswap:
            try: util.subp(("swapon", "-a"))
            except: warn("Failed to enable swap")

        for d in dirs:
            if os.path.exists(d): continue
            try: os.makedirs(d)
            except: warn("Failed to make '%s' config-mount\n",d)

        try: util.subp(("mount","-a"))
        except: pass
    


    
def apply_credentials(keys, user, disable_root):
    keys = set(keys)
    if user:
        setup_user_keys(keys, user, '')
 
    if disable_root:
        key_prefix = 'command="echo \'Please login as the %s user rather than root user.\';echo;sleep 10" ' % user
    else:
        key_prefix = ''

    setup_user_keys(keys, 'root', key_prefix)

def setup_user_keys(keys, user, key_prefix):
    import pwd
    saved_umask = os.umask(077)

    pwent = pwd.getpwnam(user)

    ssh_dir = '%s/.ssh' % pwent.pw_dir
    if not os.path.exists(ssh_dir):
        os.mkdir(ssh_dir)
        os.chown(ssh_dir, pwent.pw_uid, pwent.pw_gid)

    authorized_keys = '%s/.ssh/authorized_keys' % pwent.pw_dir
    fp = open(authorized_keys, 'a')
    fp.write(''.join(['%s%s\n' % (key_prefix, key) for key in keys]))
    fp.close()

    os.chown(authorized_keys, pwent.pw_uid, pwent.pw_gid)

    os.umask(saved_umask)

def send_ssh_keys_to_console():
    send_keys_sh = """
    {
    echo
    echo "#############################################################"
    echo "-----BEGIN SSH HOST KEY FINGERPRINTS-----"
    ssh-keygen -l -f /etc/ssh/ssh_host_rsa_key.pub
    ssh-keygen -l -f /etc/ssh/ssh_host_dsa_key.pub
    echo "-----END SSH HOST KEY FINGERPRINTS-----"
    echo "#############################################################"
    } | logger -p user.info -s -t "ec2"
    """
    subprocess.call(('sh', '-c', send_keys_sh))


def warn(str):
   sys.stderr.write("Warning:%s\n" % str)

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

        try: util.write_file(ent['filename'], source + "\n")
        except:
            elst.append([source, "failed write to file %s" % ent['filename']])

    return(elst)


def generate_sources_list(mirror):
    stdout, stderr = subprocess.Popen(['lsb_release', '-cs'], stdout=subprocess.PIPE).communicate()
    codename = stdout.strip()

    util.render_to_file('sources.list', '/etc/apt/sources.list', \
        { 'mirror' : mirror, 'codename' : codename })

def handle_updates_check(cfg):
    if not util.get_cfg_option_bool(cfg, 'updates-check', True):
        return
    build_info = "/etc/cloud/build.info"
    if not os.path.isfile(build_info):
        warn("no %s file" % build_info)

    avail="%s/%s" % ( cloudinit.datadir, "available.build" )
    cmd=( "uec-query-builds", "--system-suite", "--config", "%s" % build_info,
          "--output", "%s" % avail, "is-update-available" )
    try:
        util.subp(cmd)
    except:
        warn("failed to execute uec-query-build for updates check")

    # add a cron entry for this hour and this minute every day
    try:
        cron=open("%s-%s" % (cronpre, "updates") ,"w")
        cron.write("%s root %s\n" % \
            (time.strftime("%M %H * * *"),' '.join(cmd)))
        cron.close()
    except:
        warn("failed to enable cron update system check")

def handle_runcmd(cfg):
    if not cfg.has_key("runcmd"):
        return
    outfile="%s/runcmd" % cloudinit.user_scripts_dir

    content="#!/bin/sh\n"
    escaped="%s%s%s%s" % ( "'", '\\', "'", "'" )
    try:
        for args in cfg["runcmd"]:
            # if the item is a list, wrap all items in single tick
            # if its not, then just write it directly
            if isinstance(args,list):
                fixed = [ ]
                for f in args:
                    fixed.append("'%s'" % str(f).replace("'",escaped))
                content="%s%s\n" % ( content, ' '.join(fixed) )
            else:
                content="%s%s\n" % ( content, str(args) )

        util.write_file(outfile,content,0700)
    except:
        warn("failed to open %s for runcmd" % outfile)
