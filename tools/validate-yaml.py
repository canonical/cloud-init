#!/usr/bin/env python

"""Try to read a YAML file and report any errors.
"""

import sys
import yaml


if __name__ == "__main__":
    bads = 0
    for fn in sys.argv[1:]:
        sys.stdout.write("%s" % (fn))
        try:
            fh = open(fn, 'rb')
            yaml.safe_load(fh.read().decode('utf-8'))
            fh.close()
            sys.stdout.write(" - ok\n")
        except Exception as e:
            sys.stdout.write(" - bad (%s)\n" % (e))
            bads += 1
    if bads > 0:
        sys.exit(1)
    else:
        sys.exit(0)

# vi: ts=4 expandtab
