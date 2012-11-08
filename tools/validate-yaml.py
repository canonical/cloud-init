#!/usr/bin/env python

"""Try to read a YAML file and report any errors.
"""

import sys

import yaml


if __name__ == "__main__":
    for fn in sys.argv[1:]:
        sys.stdout.write("%s" % (fn))
        try:
            fh = open(fn, 'r')
            yaml.safe_load(fh.read())
            fh.close()
            sys.stdout.write(" - ok\n")
        except Exception, e:
            sys.stdout.write(" - bad (%s)\n" % (e))
