#!/usr/bin/python3
import sys
import os
import itertools as it
import functools

print("HERE")

from cloudinit import netinfo

from cloudinit import log as logging
#from distutils import log as logging
cfg = {
    'datasource': {'NoCloud': {'fs_label': None}}
}

logging.setupLogging(cfg)



print("%s\n" % (netinfo.debug_info()))
