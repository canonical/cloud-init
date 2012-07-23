# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Hafliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#    Author: Joe VLcek <JVLcek@RedHat.com>
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

import time
import os
import os.path

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util
from cloudinit.util import ProcessExecutionError

LOG = logging.getLogger(__name__)

# Needed file paths
CLOUD_INFO_FILE = '/etc/sysconfig/cloud-info'
MEDIA_DIR = '/media/userdata'

# Deltacloud file name contains deltacloud. Those not using
# Deltacloud but instead instrumenting the injection, could
# drop deltacloud from the file name.
DELTACLOUD_USER_DATA_FILE = MEDIA_DIR + '/deltacloud-user-data.txt'
USER_DATA_FILE = MEDIA_DIR + '/user-data.txt'

# Shell command lists
CMD_DMI_SYSTEM = ['/usr/sbin/dmidecode', '--string', 'system-product-name']
CMD_PROBE_FLOPPY = ['/sbin/modprobe', 'floppy']
CMD_MNT_FLOPPY = ['/bin/mount', '/dev/fd0', MEDIA_DIR]
CMD_MNT_CDROM = ['/bin/mount', '/dev/cdrom', MEDIA_DIR]

# Retry times and sleep secs between each try
RETRY_TIMES = 3
SLEEP_SECS = 3

META_DATA_NOT_SUPPORTED = {
    'block-device-mapping': {},
    'instance-id': 455,
    'local-hostname': 'localhost',
    'placement': {},
    }


class DataSourceAltCloud(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.dsmode = 'local'
        self.seed = None
        self.cmdline_id = "ds=nocloud"
        self.seed_dir = os.path.join(paths.seed_dir, 'nocloud')
        self.supported_seed_starts = ("/", "file://")

    def __str__(self):
        mstr = "%s [seed=%s][dsmode=%s]" % (util.obj_name(self),
                                            self.seed, self.dsmode)
        return mstr

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
                cloud_info = open(CLOUD_INFO_FILE)
                cloud_type = cloud_info.read().strip().upper()
                cloud_info.close()
            except:
                util.logexc(LOG, 'Unable to access cloud info file.')
                return False
        else:
            cloud_type = self.get_cloud_type()

        LOG.debug('cloud_type: ' + str(cloud_type))

        # Simple retry logic around user_data_<type>() methods
        tries = RETRY_TIMES
        sleep_secs = SLEEP_SECS
        while tries > 0:
            if 'RHEV' in cloud_type:
                if self.user_data_rhevm():
                    return True
            elif 'VSPHERE' in cloud_type:
                if self.user_data_vsphere():
                    return True
            else:
                # there was no recognized alternate cloud type.
                # suggesting this handler should not be used.
                return False

            time.sleep(sleep_secs)
            tries -= 1
            sleep_secs *= 3

        # Retry loop exhausted
        return False

    def user_data_rhevm(self):
        '''
        RHEVM specific userdata read

         If on RHEV-M the user data will be contained on the
         floppy device in file <USER_DATA_FILE>
         To access it:
           modprobe floppy
           mkdir <MEDIA_DIR>
           mount /dev/fd0 <MEDIA_DIR>
           mount /dev/fd0 <MEDIA_DIR> # NOTE: -> /dev/
           read <MEDIA_DIR>/<USER_DATA_FILE>
        '''

        # modprobe floppy
        try:
            cmd = CMD_PROBE_FLOPPY
            (cmd_out, _err) = util.subp(cmd)
            LOG.debug(('Command: %s\nOutput%s') % (' '.join(cmd), cmd_out))
        except ProcessExecutionError, _err:
            util.logexc(LOG, (('Failed command: %s\n%s') % \
                (' '.join(cmd), _err.message)))
            return False
        except OSError, _err:
            util.logexc(LOG, (('Failed command: %s\n%s') % \
                (' '.join(cmd), _err.message)))
            return False

        # mkdir <MEDIA_DIR> dir just in case it isn't already.
        try:
            os.makedirs(MEDIA_DIR)
        except OSError, (_err, strerror):
            if _err is not 17:
                LOG.debug(('makedirs(<MEDIA_DIR>) failed: %s \nError: %s') % \
                    (_err, strerror))
                return False

        # mount /dev/fd0 <MEDIA_DIR>
        try:
            cmd = CMD_MNT_FLOPPY
            (cmd_out, _err) = util.subp(cmd)
            LOG.debug(('Command: %s\nOutput%s') % (' '.join(cmd), cmd_out))
        except ProcessExecutionError, _err:
            # Ignore failure: already mounted
            if 'ALREADY MOUNTED' not in str(_err.message).upper():
                util.logexc(LOG, (('Failed command: %s\n%s') % \
                    (' '.join(cmd), _err.message)))
                return False
        except OSError, _err:
            util.logexc(LOG, (('Failed command: %s\n%s') % \
                (' '.join(cmd), _err.message)))
            return False

        # This could be done using "with open()" but that's not available
        # in Python 2.4 as used on RHEL5
        # First try DELTACLOUD_USER_DATA_FILE. If that fails then try
        # USER_DATA_FILE.
        try:
            user_data_file = open(DELTACLOUD_USER_DATA_FILE, 'r')
            user_data = user_data_file.read().strip()
            user_data_file.close()
        except:
            try:
                user_data_file = open(USER_DATA_FILE, 'r')
                user_data = user_data_file.read().strip()
                user_data_file.close()
            except:
                util.logexc(LOG, ('Failed accessing RHEVm user data file.'))
                try:
                    user_data_file.close()
                except:
                    pass
                return False

        self.userdata_raw = user_data
        self.metadata = META_DATA_NOT_SUPPORTED

        return True

    def user_data_vsphere(self):
        '''
        VSphere specific userdata read

        If on vSphere the user data will be contained on the
        floppy device in file <USER_DATA_FILE>
        To access it:
           mkdir <MEDIA_DIR> dir just in case it isn't already.
           mount /dev/cdrom <MEDIA_DIR> # NOTE: -> /dev/cdrom
           read <MEDIA_DIR>/<USER_DATA_FILE>
        '''

        # mkdir <MEDIA_DIR> dir just in case it isn't already.
        try:
            os.makedirs(MEDIA_DIR)
        except OSError, (_err, strerror):
            if _err is not 17:
                LOG.debug(('makedirs(<MEDIA_DIR>) failed: %s \nError: %s') % \
                    (_err, strerror))
                return False

        # mount /dev/cdrom <MEDIA_DIR>
        try:
            cmd = CMD_MNT_CDROM
            (cmd_out, _err) = util.subp(cmd)
            LOG.debug(('Command: %s\nOutput%s') % (' '.join(cmd), cmd_out))
        except ProcessExecutionError, _err:
            # Ignore failure: already mounted
            if 'ALREADY MOUNTED' not in str(_err.message).upper():
                LOG.debug(('Failed command: %s\n%s') % \
                    (' '.join(cmd), _err.message))
                return False
        except OSError, _err:
            LOG.debug(('Failed command: %s\n%s') % \
                (' '.join(cmd), _err.message))
            return False

        # This could be done using "with open()" but that's not available
        # in Python 2.4 as used on RHEL5
        # First try DELTACLOUD_USER_DATA_FILE. If that fails then try
        # USER_DATA_FILE.
        try:
            user_data_file = open(DELTACLOUD_USER_DATA_FILE, 'r')
            user_data = user_data_file.read().strip()
            user_data_file.close()
        except:
            try:
                user_data_file = open(USER_DATA_FILE, 'r')
                user_data = user_data_file.read().strip()
                user_data_file.close()
            except:
                LOG.debug('Failed accessing vSphere user data file.')
                try:
                    user_data_file.close()
                except:
                    pass
                return False

        self.userdata_raw = user_data
        self.metadata = META_DATA_NOT_SUPPORTED
        return True

# Used to match classes to dependencies
datasources = [
  (DataSourceAltCloud, (sources.DEP_FILESYSTEM, )),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
