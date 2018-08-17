# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

'''Cloud-init apport interface'''

try:
    from apport.hookutils import (
        attach_file, attach_root_command_outputs, root_command_output)
    has_apport = True
except ImportError:
    has_apport = False


KNOWN_CLOUD_NAMES = [
    'AliYun',
    'AltCloud',
    'Amazon - Ec2',
    'Azure',
    'Bigstep',
    'Brightbox',
    'CloudSigma',
    'CloudStack',
    'DigitalOcean',
    'GCE - Google Compute Engine',
    'Hetzner Cloud',
    'IBM - (aka SoftLayer or BlueMix)',
    'LXD',
    'MAAS',
    'NoCloud',
    'OpenNebula',
    'OpenStack',
    'Oracle',
    'OVF',
    'OpenTelekomCloud',
    'Scaleway',
    'SmartOS',
    'VMware',
    'Other']

# Potentially clear text collected logs
CLOUDINIT_LOG = '/var/log/cloud-init.log'
CLOUDINIT_OUTPUT_LOG = '/var/log/cloud-init-output.log'
USER_DATA_FILE = '/var/lib/cloud/instance/user-data.txt'  # Optional


def attach_cloud_init_logs(report, ui=None):
    '''Attach cloud-init logs and tarfile from 'cloud-init collect-logs'.'''
    attach_root_command_outputs(report, {
        'cloud-init-log-warnings':
            'egrep -i "warn|error" /var/log/cloud-init.log',
        'cloud-init-output.log.txt': 'cat /var/log/cloud-init-output.log'})
    root_command_output(
        ['cloud-init', 'collect-logs', '-t', '/tmp/cloud-init-logs.tgz'])
    attach_file(report, '/tmp/cloud-init-logs.tgz', 'logs.tgz')


def attach_hwinfo(report, ui=None):
    '''Optionally attach hardware info from lshw.'''
    prompt = (
        'Your device details (lshw) may be useful to developers when'
        ' addressing this bug, but gathering it requires admin privileges.'
        ' Would you like to include this info?')
    if ui and ui.yesno(prompt):
        attach_root_command_outputs(report, {'lshw.txt': 'lshw'})


def attach_cloud_info(report, ui=None):
    '''Prompt for cloud details if available.'''
    if ui:
        prompt = 'Is this machine running in a cloud environment?'
        response = ui.yesno(prompt)
        if response is None:
            raise StopIteration  # User cancelled
        if response:
            prompt = ('Please select the cloud vendor or environment in which'
                      ' this instance is running')
            response = ui.choice(prompt, KNOWN_CLOUD_NAMES)
            if response:
                report['CloudName'] = KNOWN_CLOUD_NAMES[response[0]]
            else:
                report['CloudName'] = 'None'


def attach_user_data(report, ui=None):
    '''Optionally provide user-data if desired.'''
    if ui:
        prompt = (
            'Your user-data or cloud-config file can optionally be provided'
            ' from {0} and could be useful to developers when addressing this'
            ' bug. Do you wish to attach user-data to this bug?'.format(
                USER_DATA_FILE))
        response = ui.yesno(prompt)
        if response is None:
            raise StopIteration  # User cancelled
        if response:
            attach_file(report, USER_DATA_FILE, 'user_data.txt')


def add_bug_tags(report):
    '''Add any appropriate tags to the bug.'''
    if 'JournalErrors' in report.keys():
        errors = report['JournalErrors']
        if 'Breaking ordering cycle' in errors:
            report['Tags'] = 'systemd-ordering'


def add_info(report, ui):
    '''This is an entry point to run cloud-init's apport functionality.

    Distros which want apport support will have a cloud-init package-hook at
    /usr/share/apport/package-hooks/cloud-init.py which defines an add_info
    function and returns the result of cloudinit.apport.add_info(report, ui).
    '''
    if not has_apport:
        raise RuntimeError(
            'No apport imports discovered. Apport functionality disabled')
    attach_cloud_init_logs(report, ui)
    attach_hwinfo(report, ui)
    attach_cloud_info(report, ui)
    attach_user_data(report, ui)
    add_bug_tags(report)
    return True

# vi: ts=4 expandtab
