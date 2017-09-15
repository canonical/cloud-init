'''Wrapper for cloudinit apport interface'''

from cloudinit.apport import add_info as cloudinit_add_info

def add_info(report, ui):
    return cloudinit_add_info(report, ui)
