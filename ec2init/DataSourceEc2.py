import DataSource

import ec2init
import boto.utils
import socket
import urllib2
import time
import cPickle

class DataSourceEc2(DataSource.DataSource):
    api_ver  = '2009-04-04'
    conffile = '/etc/ec2-init/ec2-config.cfg'
    cachedir = ec2init.cachedir + '/ec2'

    location_locale_map = { 
        'us' : 'en_US.UTF-8',
        'eu' : 'en_GB.UTF-8'
    }

    location_archive_map = { 
        'us' : 'http://us.ec2.archive.ubuntu.com/ubuntu',
        'eu' : 'http://eu.ec2.archive.ubuntu.com/ubuntu'
    }

    def __init__(self):
        self.meta_data_base_url = 'http://169.254.169.254/%s/meta-data' % self.api_ver
        self.userdata_base_url = 'http://169.254.169.254/%s/user-data' % self.api_ver

    def get_data(self):
        try:
            udf = open(self.cachedir + "/user-data.pkl")
            self.userdata_raw = cPickle.load(udf)
            udf.close()

            mdf = open(self.cachedir + "/meta-data.pkl")
            self.metadata = cPickle.load(mdf)
            mdf.close()

            return True
        except:
            pass

        try:
            if not self.wait_for_metadata_service():
                return False
            self.metadata = boto.utils.get_instance_userdata(api_ver)
            self.userdata_raw = boto.utils.get_instance_metadata(api_ver)
        except Exception as e:
            print e
            return False

    def get_instance_id(self):
        return(self.metadata['instance-id'])

    def wait_or_bail(self):
        if self.wait_for_metadata_service():
            return True
        else:
            bailout_command = self.get_cfg_option_str('bailout_command')
            if bailout_command:
                os.system(bailout_command)
            return False

    def get_cfg_option_str(self, key, default=None):
        return self.config.get(key, default)

    def get_ssh_keys(self):
        conn = urllib2.urlopen('%s/public-keys/' % self.meta_data_base_url)
        data = conn.read()
        keyids = [line.split('=')[0] for line in data.split('\n')]
        return [urllib2.urlopen('%s/public-keys/%d/openssh-key' % (self.meta_data_base_url, int(keyid))).read().rstrip() for keyid in keyids]

#    def get_userdata(self):
#        return boto.utils.get_instance_userdata()
#
#    def get_instance_metadata(self):
#        self.instance_metadata = getattr(self, 'instance_metadata', boto.utils.get_instance_metadata())
#        return self.instance_metadata 

    def get_ami_id(self):
        return self.get_instance_metadata()['ami-id']
    
    def get_availability_zone(self):
        conn = urllib2.urlopen('%s/placement/availability-zone' % self.meta_data_base_url)
        return conn.read()

    def get_hostname(self):
        hostname = self.get_instance_metadata()['local-hostname']
        hostname = hostname.split('.')[0]
        return hostname

    def get_mirror_from_availability_zone(self, availability_zone):
        # availability is like 'us-west-1b' or 'eu-west-1a'
        try:
            host="%s.ec2.archive.ubuntu.com" % availability_zone[:-1]
            socket.getaddrinfo(host, None, 0, socket.SOCK_STREAM)
            return 'http://%s/ubuntu/' % host
        except:
            return 'http://archive.ubuntu.com/ubuntu/'

    def wait_for_metadata_service(self, sleeps = 10):
        sleeptime = 1
        for x in range(sleeps):
            s = socket.socket()
            try:
                address = '169.254.169.254'
                port = 80
                s.connect((address,port))
                s.close()
                return True
            except socket.error, e:
                print "sleeping %s" % sleeptime
                time.sleep(sleeptime)
                #timeout = timeout * 2
        return False

    def get_location_from_availability_zone(self, availability_zone):
        if availability_zone.startswith('us-'):
            return 'us'
        elif availability_zone.startswith('eu-'):
            return 'eu'
        raise Exception('Could not determine location')

    def get_public_ssh_keys(self):
        keys = []
        if not self.metadata.has_key('public-keys'): return([])
        for keyname, klist in self.metadata['public-keys'].items():
            for pkey in klist:
                # there is an empty string at the end of the keylist, trim it
                if pkey:
                    keys.append(pkey)

        return(keys)
