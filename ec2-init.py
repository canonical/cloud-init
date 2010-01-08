#!/usr/bin/python

import subprocess
from Cheetah.Template import Template
import sys

import ec2init

def warn(str):
    sys.stderr.write(str)

def main():
    cloud = ec2init.EC2Init()

    data = None
    try:
        cloud.get_data_source()
    except Exception as e:
        print e
        sys.stderr.write("Failed to get instance data")
        sys.exit(1)

    #print "user data is:" + cloud.get_user_data()

    # store the metadata
    cloud.update_cache()

    # parse the user data (ec2-run-userdata.py)
    try:
        cloud.sem_and_run("consume_userdata", "once-per-instance",
            cloud.consume_userdata,[],False)
    except:
        warn("consuming user data failed!")
        raise

    # set the defaults (like what ec2-set-defaults.py did)
    try:
        generate_sources_list(cloud.get_mirror())
        apply_locale(cloud.get_locale())
    except:
        warn("failed to set defaults")

    # set the ssh keys up
    cloud.apply_credentials()

    # finish, send the cloud-config event
    cloud.initctl_emit()

    sys.exit(0)

def render_to_file(template, outfile, searchList):
    t = Template(file='/etc/ec2-init/templates/%s.tmpl' % template, searchList=[searchList])
    f = open(outfile, 'w')
    f.write(t.respond())
    f.close()
    
def apply_locale(locale):
    subprocess.Popen(['locale-gen', locale]).communicate()
    subprocess.Popen(['update-locale', locale]).communicate()

    render_to_file('default-locale', '/etc/default/locale', { 'locale' : locale })

def generate_sources_list(mirror):
    stdout, stderr = subprocess.Popen(['lsb_release', '-cs'], stdout=subprocess.PIPE).communicate()
    codename = stdout.strip()

    render_to_file('sources.list', '/etc/apt/sources.list', { 'mirror' : mirror, 'codename' : codename })

if __name__ == '__main__':
    main()
