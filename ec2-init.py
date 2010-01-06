#!/usr/bin/python

import subprocess
from Cheetah.Template import Template
import sys

import ec2init

def main():
    cloud = ec2init.EC2Init()

    data = None
    try:
        cloud.get_data_source()
    except Exception as e:
        print e
        sys.stderr.write("Failed to get instance data")
        sys.exit(1)

    print "user data is:" + cloud.get_user_data()

    # store the metadata
    cloud.update_cache()

    # parse the user data (ec2-run-userdata.py)
    # TODO: cloud.consume_user_data()

    # set the defaults (like what ec2-set-defaults.py did)
    # TODO: cloud.set_defaults()

    # set the ssh keys up
    # TODO: cloud.enable_authorized_keys()

    # finish, send the cloud-config event
    cloud.initctl_emit()

    sys.exit(0)

if __name__ == '__main__':
    main()
