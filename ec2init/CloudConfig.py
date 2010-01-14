#
#    Common code for the EC2 configuration files in Ubuntu
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
import ec2init
import subprocess
import os

per_instance="once-per-instance"

class CloudConfig():
    cfgfile = None
    handlers = { }
    cfg = None
    old_conffile = '/etc/ec2-init/ec2-config.cfg'

    def __init__(self,cfgfile):
        self.cfg = self.get_config_obj(cfgfile)
        self.cloud = ec2init.EC2Init()
        self.cloud.get_data_source()
        self.add_handler('apt-update-upgrade', self.h_apt_update_upgrade)
        self.add_handler('config-ssh')

    def get_config_obj(self,cfgfile):
        str=""
        # support reading the old ConfigObj format file and turning it
        # into a yaml string
        try:
            f = file(self.old_conffile)
            str+=file.read().replace('=',': ')
            f.close()
        except:
            pass

        f = file(cfgfile)
        cfg=yaml.load(str + f.read())
        f.close()
        return(cfg)

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

	def check_for_updates(self):
		value = self.cfg['apt_update']
		return value

	def check_for_upgrade(self):
		value = self.cfg['apt_upgrade']
		return value
	
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

	def add_ppa(self):
		#value = self.cfg['apt_sources']
		for ent in self.cfg['apt_sources']:
			ppa = ent['source']
			where = ppa.find('ppa:')
			if where != -1:
			  return ppa

	def add_custom_repo(self):
		sources = []
		value = self.cfg['apt_sources']
		for ent in self.cfg['apt_sources']:
			if ent.has_key('keyserver'):
				keyserver = ent['keyserver']
			if ent.has_key('keyid'):
				keyid = ent['keyid']
			if ent.has_key('filename'):
				filename = ent['filename']
			source = ent['source']
			if source.startswith("deb"):
				sources.append(source)

		return (keyserver,sources,keyid,filename)

    def handle(self, name, args):
        handler = None
        freq = None
        try:
            (handler, freq) = self.get_handler_info(name)
        except:
            raise Exception("Unknown config key %s\n" % name)

        self.cloud.sem_and_run(name, freq, handler, [ name, args ])

    def h_apt_update_upgrade(self,name,args):
        update = get_cfg_option_bool(self.cfg, 'apt_update', False)
        upgrade = get_cfg_option_bool(self.cfg, 'apt_upgrade', False)
           
        print "update = %s , upgrade = %s\n" % (update,upgrade)
        if update or upgrade:
            #retcode = subprocess.call(list)
		    subprocess.Popen(['apt-get', 'update']).communicate()

        if upgrade:
            e=os.environ.copy()
            e['DEBIAN_FRONTEND']='noninteractive'
            subprocess.Popen(['apt-get', 'upgrade', '--assume-yes'], env=e).communicate()

        return(True)

    def h_config_ssh(self,name,args):
        print "Warning, not doing anything for config %s" % name
        if False:
            # if there are keys in cloud-config, use them
            # TODO: need to get keys from cloud-config if present
            # and replace those in /etc/ssh
            pass
        else:
            # if not, generate them
            clean_and_gen='rm -f /etc/ssh/ssh_host_*_key*; ' + \
                'ssh-keygen -f /etc/ssh/ssh_host_rsa_key -t rsa -N ""; ' + \
                'ssh-keygen -f /etc/ssh/ssh_host_dsa_key -t rsa -N ""; '
            subprocess.call(('sh', '-c', clean_and_gen))

        try:
            user = get_cfg_option_str(self.cfg,'user')
            disable_root = get_cfg_option_bool(self.cfg, "disable_root", True)
            keys = self.cloud.get_public_ssh_keys()
            apply_credentials(keys,user,disable_root)
        except:
            warn("applying credentials failed!\n")

        send_ssh_keys_to_console()

        subprocess.call(('restart', 'ssh'))

    def h_ec2_ebs_mounts(self,name,args):
        print "Warning, not doing anything for config %s" % name

    def h_config_setup_raid(self,name,args):
        print "Warning, not doing anything for config %s" % name

    def h_config_runurl(self,name,args):
        print "Warning, not doing anything for config %s" % name


def get_cfg_option_bool(yobj, key, default=False):
    if not yobj.has_key(key): return default
    val = yobj[key]
    if yobj[key] in [ True, '1', 'on', 'yes', 'true']:
        return True
    return False

def get_cfg_option_str(yobj, key, default=None):
    if not yobj.has_key(key): return default
    return yobj[key]

def read_conf(fname):
	stream = file(fname)
	conf = yaml.load(stream)
	stream.close()
	return conf

def apply_credentials(keys, user, disable_root):
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

