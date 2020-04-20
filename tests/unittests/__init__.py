# This file is part of cloud-init. See LICENSE file for license information.

try:
    # For test cases, avoid the following UserWarning to stderr:
    # You don't have the C version of NameMapper installed ...
    from Cheetah import NameMapper as _nm
    _nm.C_VERSION = True
except ImportError:
    pass

# vi: ts=4 expandtab
