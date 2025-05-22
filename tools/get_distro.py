#!/usr/bin/env python3
import os
import sys

try:
    from cloudinit.util import get_linux_distro
except ImportError:
    _tdir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, _tdir)
    from cloudinit.util import get_linux_distro

print(get_linux_distro()[0])
