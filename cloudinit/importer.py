# vim: tabstop=4 shiftwidth=4 softtabstop=4

import sys


def import_module(module_name):
    try:
        __import__(module_name)
        return sys.modules.get(module_name, None)
    except ImportError as err:
        raise RuntimeError('Could not load module %s: %s' % (module_name, err))
