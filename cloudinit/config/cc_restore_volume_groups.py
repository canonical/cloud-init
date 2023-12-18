# =================================================================
#
#    (c) Copyright IBM Corp. 2015 
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
# =================================================================

import os
import re

from cloudinit.settings import PER_INSTANCE
from cloudinit import util, subp

frequency = PER_INSTANCE


IMPORTVG = "/usr/sbin/importvg"
LSPV = "/usr/sbin/lspv"
# an example of lspv output is shown below (where space = any whitespace):
# <disk_name> <physical_volume_id> <volume_group_name> <active>
LSVG = "/usr/sbin/lsvg"
MOUNT = "/usr/sbin/mount"

MAPPING_FILE = '/opt/freeware/etc/cloud/pvid_to_vg_mappings'


def handle(name, _cfg, _cloud, log, _args):
    log.debug('Attempting to restore non-rootVG volume groups.')

    if not os.access(MAPPING_FILE, os.R_OK):
        log.warn('Physical volume ID to volume group mapping file "%s" does '
                 'not exist or permission to read the file does not exist. '
                 'Ensure that the file exists and the permissions for it are '
                 'correct.' % MAPPING_FILE)
        return

    with open(MAPPING_FILE, 'r') as f:
        mapping_file_lines = f.readlines()

    pvid_to_vg_map = parse_mapping_file(log, mapping_file_lines)

    for physical_volume_id, volume_group_name in list(pvid_to_vg_map.items()):
        if volume_group_name.lower() == 'none':
            # skip any physical volumes that were not associated with any
            # volume group on the captured system
            log.warn('The physical volume with ID "%s" was associated '
                     'with a volume group labeled "%s" on the '
                     'captured system. This physical volume will not '
                     'be associated with a volume group.' %
                     (physical_volume_id, volume_group_name))
            continue

        # Run lspv for each captured physical volume ID, so that any
        # changes caused by importvg are picked up the next time
        # through the loop.  The effect of this is that importvg is
        # only run once per volume group: "The PhysicalVolume parameter
        # specifies only one physical volume to identify the volume group; any
        # remaining physical volumes (those belonging to the same volume group)
        # are found the importvg command and included in the import".
        pv = get_physical_volume_from_lspv(log, physical_volume_id)

        if pv is None:
            log.warn('The physical volume with ID "%s" was not found, so it '
                     'cannot be associated with volume group "%s".' %
                     (physical_volume_id, volume_group_name))
            continue

        if (pv['volume_group'] is None and not pv['active']):
            # If the volume group is not set and the disk is not active,
            # then set it.
            set_volume_group(log, pv['hdisk'], volume_group_name)

    # Ensure that all volume groups captured are now present
    expected_volume_groups = set(vg for vg in list(pvid_to_vg_map.values()))
    existing_volume_groups = get_existing_volume_groups(log)
    for group in expected_volume_groups:
        if group not in existing_volume_groups:
            msg = 'Volume group "%s" is not present.' % group
            log.error(msg)
            raise Exception(msg)

    # Ensure that all disks get mounted that are marked in /etc/filesystems as
    # auto-mounting. These disks would normally get auto-mounted at system
    # startup, but not after importvg. Note that some errors may appear for
    # filesystems that are already mounted.
    try:
        out = subp.subp([MOUNT, "all"])[0]
        log.debug(out)
    except subp.ProcessExecutionError as e:
        log.debug('Attempting to mount disks marked as auto-mounting resulted '
                  'in errors. This is likely due to attempting to mount '
                  'filesystems that are already mounted, therefore '
                  'ignoring: %s.' % e)

    # Clean up the mapping file
    os.remove(MAPPING_FILE)


def parse_mapping_file(log, lines):
    '''
    Parses the lines, skipping any blank lines, expecting the each line to be
    a volume group name, whitespace, then a physical volume ID.  E.g.:
        <vol_group_name1> <physical_vol_id1>
        <vol_group_name1> <physical_vol_id2>
        <vol_group_name2> <physical_vol_id3>
        <vol_group_name3> <physical_vol_id4>
    Note that the order does not matter. Physical volume IDs that are "none"
    and volume group names that are "rootvg" will raise exceptions as the
    script generating the mapping file should not include those entries.

    Returns a dictionary with keys of physical volume IDs mapping to their
    corresponding volume group name.
    '''
    pvid_to_vg_map = {}

    for line in lines:
        if line.strip() == '':
            continue

        split_line = line.strip().split()
        if len(split_line) != 2:
            msg = ('Physical volume ID to volume group mapping file contains '
                   'lines in an invalid format. Each line should contain a '
                   'volume group name, a single space, then a physical volume '
                   'ID. Invalid line: "%s".' % line.strip())
            log.error(msg)
            raise Exception(msg)

        volume_group_name, physical_volume_id = tuple(line.split())
        if physical_volume_id.lower() == 'none':
            msg = ('Physical volume ID parsed as "%s", but there should be no '
                   'entries in the mapping file like this.' %
                   physical_volume_id)
            log.error(msg)
            raise Exception(msg)
        if volume_group_name.lower() == 'rootvg':
            msg = ('Volume group name parsed as "%s", but there should be no '
                   'entries in the mapping file like this.' %
                   volume_group_name)
            log.error(msg)
            raise Exception(msg)

        pvid_to_vg_map[physical_volume_id] = volume_group_name

    return pvid_to_vg_map


def get_physical_volume_from_lspv(log, physical_volume_id):
    '''
    The output of the lspv command for a specific physical volume ID is
    returned from this method as a dictionary representing the physical volume
    ID. If the lspv command output does not contain any output corresponding
    to the given physical volume ID, then None is returned.

    The dictionary returned is of the following format:
        {'hdisk': <hdisk_name>,
         'physical_volume_id': <physical_vol_id>,
         'volume_group': <vol_group>,
         'active': <active, boolean>}
    '''
    try:
        env = os.environ
        env['LANG'] = 'C'
        lspv_out = subp.subp([LSPV], env=env)[0].strip()
    except subp.ProcessExecutionError:
        util.logexc(log, 'Failed to run lspv command.')
        raise

    lspv_out_specific_pvid = re.findall(r'.*%s.*' % physical_volume_id,
                                        lspv_out)
    if len(lspv_out_specific_pvid) < 1:
        return None

    lspv_specific_pvid = lspv_out_specific_pvid[0].split()

    if len(lspv_specific_pvid) < 3:
        msg = ('Output from lspv does not match the expected format. The '
               'expected output is of of the form "<disk_name> '
               '<physical_volume_id> <volume_group_name> <active>". The '
               'actual output was: "%s".' % lspv_out_specific_pvid)
        log.error(msg)
        raise Exception(msg)

    volume_group = lspv_specific_pvid[2]
    if volume_group.lower() == 'none':
        volume_group = None

    physical_volume = {
        'hdisk': lspv_specific_pvid[0],
        'physical_volume_id': lspv_specific_pvid[1],
        'volume_group': volume_group,
        'active': 'active' in lspv_specific_pvid
    }

    return physical_volume


def set_volume_group(log, hdisk, volume_group_name):
    '''
    Uses the importvg command to set the volume group for the given hdisk.
    '''
    try:
        out = subp.subp([IMPORTVG, "-y", volume_group_name, hdisk])[0]
        log.debug(out)
    except subp.ProcessExecutionError:
        util.logexc(log, 'Failed to set the volume group for disk '
                    '%s.' % hdisk)
        raise


def get_existing_volume_groups(log):
    '''
    Uses the lsvg command to get all existing volume groups.
    '''
    volume_groups = []
    try:
        env = os.environ
        env['LANG'] = 'C'
        lsvg_out = subp.subp([LSVG], env=env)[0].strip()
        volume_groups = lsvg_out.split('\n')
        volume_groups = [vg.strip() for vg in volume_groups]
    except subp.ProcessExecutionError:
        util.logexc(log, 'Failed to run lsvg command.')
        raise
    return volume_groups
