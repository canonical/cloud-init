#    Copyright (C) 2016 Canonical Ltd.
#    Copyright (C) 2016 VMware INC.
#
#    Author: Maitreyee Saikia <msaikia@vmware.com>
#
#    This file is part of cloud-init. See LICENSE file for license information.


import logging
import os

from cloudinit import util

LOG = logging.getLogger(__name__)


class PasswordConfigurator(object):
    """
    Class for changing configurations related to passwords in a VM. Includes
    setting and expiring passwords.
    """
    def configure(self, passwd, resetPasswd, distro):
        """
        Main method to perform all functionalities based on configuration file
        inputs.
        @param passwd: encoded admin password.
        @param resetPasswd: boolean to determine if password needs to be reset.
        @return cfg: dict to be used by cloud-init set_passwd code.
        """
        LOG.info('Starting password configuration')
        if passwd:
            passwd = util.b64d(passwd)
        allRootUsers = []
        for line in open('/etc/passwd', 'r'):
            if line.split(':')[2] == '0':
                allRootUsers.append(line.split(':')[0])
        # read shadow file and check for each user, if its uid0 or root.
        uidUsersList = []
        for line in open('/etc/shadow', 'r'):
            user = line.split(':')[0]
            if user in allRootUsers:
                uidUsersList.append(user)
        if passwd:
            LOG.info('Setting admin password')
            distro.set_passwd('root', passwd)
        if resetPasswd:
            self.reset_password(uidUsersList)
        LOG.info('Configure Password completed!')

    def reset_password(self, uidUserList):
        """
        Method to reset password. Use passwd --expire command. Use chage if
        not succeeded using passwd command. Log failure message otherwise.
        @param: list of users for which to expire password.
        """
        LOG.info('Expiring password.')
        for user in uidUserList:
            try:
                util.subp(['passwd', '--expire', user])
            except util.ProcessExecutionError as e:
                if os.path.exists('/usr/bin/chage'):
                    util.subp(['chage', '-d', '0', user])
                else:
                    LOG.warning('Failed to expire password for %s with error: '
                                '%s', user, e)

# vi: ts=4 expandtab
