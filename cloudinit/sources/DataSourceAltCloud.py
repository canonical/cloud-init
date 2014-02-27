# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Joe VLcek <JVLcek@RedHat.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

'''
This file contains code used to gather the user data passed to an
instance on RHEVm and vSphere.
'''

import errno
import os
import os.path

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

from cloudinit.util import ProcessExecutionError

LOG = logging.getLogger(__name__)

# Needed file paths
CLOUD_INFO_FILE = '/etc/sysconfig/cloud-info'

# Shell command lists
CMD_DMI_SYSTEM = ['/usr/sbin/dmidecode', '--string', 'system-product-name']
CMD_PROBE_FLOPPY = ['/sbin/modprobe', 'floppy']
CMD_UDEVADM_SETTLE = ['/sbin/udevadm', 'settle', '--quiet', '--timeout=5']

META_DATA_NOT_SUPPORTED = {
    'block-device-mapping': {},
    'instance-id': 455,
    'local-hostname': 'localhost',
    'placement': {},
}


def read_user_data_callback(mount_dir):
    '''
    Description:
        This callback will be applied by util.mount_cb() on the mounted
        file.

        Deltacloud file name contains deltacloud. Those not using
        Deltacloud but instead instrumenting the injection, could
        drop deltacloud from the file name.

    Input:
        mount_dir - Mount directory

    Returns:
        User Data

    '''

    deltacloud_user_data_file = mount_dir + '/deltacloud-user-data.txt'
    user_data_file = mount_dir + '/user-data.txt'

    # First try deltacloud_user_data_file. On failure try user_data_file.
    try:
        user_data = util.load_file(deltacloud_user_data_file).strip()
    except IOError:
        try:
            user_data = util.load_file(user_data_file).strip()
        except IOError:
            util.logexc(LOG, 'Failed accessing user data file.')
            return None

    return user_data


class DataSourceAltCloud(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed = None
        self.supported_seed_starts = ("/", "file://")

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def get_cloud_type(self):
        '''
        Description:
            Get the type for the cloud back end this instance is running on
            by examining the string returned by:
            dmidecode --string system-product-name

            On VMWare/vSphere dmidecode returns: RHEV Hypervisor
            On VMWare/vSphere dmidecode returns: VMware Virtual Platform

        Input:
            None

        Returns:
            One of the following strings:
            'RHEV', 'VSPHERE' or 'UNKNOWN'

        '''

        uname_arch = os.uname()[4]
        if uname_arch.startswith("arm") or uname_arch == "aarch64":
            # Disabling because dmidecode in CMD_DMI_SYSTEM crashes kvm process
            LOG.debug("Disabling AltCloud datasource on arm (LP: #1243287)")
            return 'UNKNOWN'

        cmd = CMD_DMI_SYSTEM
        try:
            (cmd_out, _err) = util.subp(cmd)
        except ProcessExecutionError, _err:
            LOG.debug(('Failed command: %s\n%s') % \
                (' '.join(cmd), _err.message))
            return 'UNKNOWN'
        except OSError, _err:
            LOG.debug(('Failed command: %s\n%s') % \
                (' '.join(cmd), _err.message))
            return 'UNKNOWN'

        if cmd_out.upper().startswith('RHEV'):
            return 'RHEV'

        if cmd_out.upper().startswith('VMWARE'):
            return 'VSPHERE'

        return 'UNKNOWN'

    def get_data(self):
        '''
        Description:
            User Data is passed to the launching instance which
            is used to perform instance configuration.

            Cloud providers expose the user data differently.
            It is necessary to determine which cloud provider
            the current instance is running on to determine
            how to access the user data. Images built with
            image factory will contain a CLOUD_INFO_FILE which
            contains a string identifying the cloud provider.

            Images not built with Imagefactory will try to
            determine what the cloud provider is based on system
            information.
        '''

        LOG.debug('Invoked get_data()')

        if os.path.exists(CLOUD_INFO_FILE):
            try:
                cloud_type = util.load_file(CLOUD_INFO_FILE).strip().upper()
            except IOError:
                util.logexc(LOG, 'Unable to access cloud info file at %s.',
                            CLOUD_INFO_FILE)
                return False
        else:
            cloud_type = self.get_cloud_type()

        LOG.debug('cloud_type: ' + str(cloud_type))

        if 'RHEV' in cloud_type:
            if self.user_data_rhevm():
                return True
        elif 'VSPHERE' in cloud_type:
            if self.user_data_vsphere():
                return True
        else:
            # there was no recognized alternate cloud type
            # indicating this handler should not be used.
            return False

        # No user data found
        util.logexc(LOG, 'Failed accessing user data.')
        return False

    def user_data_rhevm(self):
        '''
        RHEVM specific userdata read

         If on RHEV-M the user data will be contained on the
         floppy device in file <user_data_file>
         To access it:
           modprobe floppy

           Leverage util.mount_cb to:
               mkdir <tmp mount dir>
               mount /dev/fd0 <tmp mount dir>
               The call back passed to util.mount_cb will do:
                   read <tmp mount dir>/<user_data_file>
        '''

        return_str = None

        # modprobe floppy
        try:
            cmd = CMD_PROBE_FLOPPY
            (cmd_out, _err) = util.subp(cmd)
            LOG.debug(('Command: %s\nOutput%s') % (' '.join(cmd), cmd_out))
        except ProcessExecutionError, _err:
            util.logexc(LOG, 'Failed command: %s\n%s', ' '.join(cmd),
                        _err.message)
            return False
        except OSError, _err:
            util.logexc(LOG, 'Failed command: %s\n%s', ' '.join(cmd),
                        _err.message)
            return False

        floppy_dev = '/dev/fd0'

        # udevadm settle for floppy device
        try:
            cmd = CMD_UDEVADM_SETTLE
            cmd.append('--exit-if-exists=' + floppy_dev)
            (cmd_out, _err) = util.subp(cmd)
            LOG.debug(('Command: %s\nOutput%s') % (' '.join(cmd), cmd_out))
        except ProcessExecutionError, _err:
            util.logexc(LOG, 'Failed command: %s\n%s', ' '.join(cmd),
                        _err.message)
            return False
        except OSError, _err:
            util.logexc(LOG, 'Failed command: %s\n%s', ' '.join(cmd),
                        _err.message)
            return False

        try:
            return_str = util.mount_cb(floppy_dev, read_user_data_callback)
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise
        except util.MountFailedError:
            util.logexc(LOG, "Failed to mount %s when looking for user data",
                        floppy_dev)

        self.userdata_raw = return_str
        self.metadata = META_DATA_NOT_SUPPORTED

        if return_str:
            return True
        else:
            return False

    def user_data_vsphere(self):
        '''
        vSphere specific userdata read

        If on vSphere the user data will be contained on the
        cdrom device in file <user_data_file>
        To access it:
           Leverage util.mount_cb to:
               mkdir <tmp mount dir>
               mount /dev/fd0 <tmp mount dir>
               The call back passed to util.mount_cb will do:
                   read <tmp mount dir>/<user_data_file>
        '''

        return_str = None
        cdrom_list = util.find_devs_with('LABEL=CDROM')
        for cdrom_dev in cdrom_list:
            try:
                return_str = util.mount_cb(cdrom_dev, read_user_data_callback)
                if return_str:
                    break
            except OSError as err:
                if err.errno != errno.ENOENT:
                    raise
            except util.MountFailedError:
                util.logexc(LOG, "Failed to mount %s when looking for user "
                            "data", cdrom_dev)

        self.userdata_raw = return_str
        self.metadata = META_DATA_NOT_SUPPORTED

        if return_str:
            return True
        else:
            return False

# Used to match classes to dependencies
# Source DataSourceAltCloud does not really depend on networking.
# In the future 'dsmode' like behavior can be added to offer user
# the ability to run before networking.
datasources = [
  (DataSourceAltCloud, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
