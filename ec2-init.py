#!/usr/bin/python

import subprocess
import sys

import cloudinit
import cloudinit.util as util

def warn(str):
    sys.stderr.write(str)

def main():
    cloud = cloudinit.EC2Init()

    try:
        cloud.get_data_source()
    except Exception as e:
        print e
        sys.stderr.write("Failed to get instance data")
        sys.exit(1)

    hostname = cloud.get_hostname()
    subprocess.Popen(['hostname', hostname]).communicate()
    #print "user data is:" + cloud.get_user_data()

    # store the metadata
    cloud.update_cache()

    # parse the user data (ec2-run-userdata.py)
    try:
        cloud.sem_and_run("consume_userdata", "once-per-instance",
            cloud.consume_userdata,[],False)
    except:
        warn("consuming user data failed!\n")
        raise

    # set the defaults (like what ec2-set-defaults.py did)
    try:
        cloud.sem_and_run("set_defaults", "once-per-instance",
            set_defaults,[ cloud ],False)
    except:
        warn("failed to set defaults\n")

    # finish, send the cloud-config event
    cloud.initctl_emit()

    sys.exit(0)

def set_defaults(cloud):
    apply_locale(cloud.get_locale())
    
def apply_locale(locale):
    subprocess.Popen(['locale-gen', locale]).communicate()
    subprocess.Popen(['update-locale', locale]).communicate()

    util.render_to_file('default-locale', '/etc/default/locale', \
        { 'locale' : locale })

if __name__ == '__main__':
    main()
