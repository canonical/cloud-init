# vi: ts=4 expandtab
#
#    Copyright (C) Red Hat, Inc.
#
#    Author: Brent Baude <bbaude@redhat.com>
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

import os
import subprocess
import itertools


def handle(_name, cfg, _cloud, log, _args):
    sm = SubscriptionManager(cfg)
    sm.log = log

    if not sm.is_registered:
        try:
            verify, verify_msg = sm._verify_keys()
            if verify is not True:
                raise SubscriptionError(verify_msg)
            cont = sm.rhn_register()
            if not cont:
                raise SubscriptionError("Registration failed or did not "
                                        "run completely")

            # Splitting up the registration, auto-attach, and servicelevel
            # commands because the error codes, messages from subman are not
            # specific enough.

            # Attempt to change the service level
            if sm.auto_attach and sm.servicelevel is not None:
                    if not sm._set_service_level():
                        raise SubscriptionError("Setting of service-level "
                                                "failed")
                    else:
                        sm.log.info("Completed auto-attach with service level")
            elif sm.auto_attach:
                if not sm._set_auto_attach():
                    raise SubscriptionError("Setting auto-attach failed")
                else:
                    sm.log.info("Completed auto-attach")

            if sm.pools is not None:
                if type(sm.pools) is not list:
                    raise SubscriptionError("Pools must in the format of a "
                                            "list.")
                return_stat = sm.addPool(sm.pools)
                if not return_stat:
                    raise SubscriptionError("Unable to attach pools {0}"
                                            .format(sm.pools))
            if (sm.enable_repo is not None) or (sm.disable_repo is not None):
                return_stat = sm.update_repos(sm.enable_repo, sm.disable_repo)
                if not return_stat:
                    raise SubscriptionError("Unable to add or remove repos")
            sm.log.info("rh_subscription plugin completed successfully")
        except SubscriptionError as e:
            sm.log.warn(e)
            sm.log.info("rh_subscription plugin did not complete successfully")
    else:
        sm.log.info("System is already registered")


class SubscriptionError(Exception):
    pass


class SubscriptionManager(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.rhel_cfg = self.cfg.get('rh_subscription', {})
        self.rhsm_baseurl = self.rhel_cfg.get('rhsm-baseurl')
        self.server_hostname = self.rhel_cfg.get('server-hostname')
        self.pools = self.rhel_cfg.get('add-pool')
        self.activation_key = self.rhel_cfg.get('activation-key')
        self.org = self.rhel_cfg.get('org')
        self.userid = self.rhel_cfg.get('username')
        self.password = self.rhel_cfg.get('password')
        self.auto_attach = self.rhel_cfg.get('auto-attach')
        self.enable_repo = self.rhel_cfg.get('enable-repo')
        self.disable_repo = self.rhel_cfg.get('disable-repo')
        self.servicelevel = self.rhel_cfg.get('service-level')
        self.subman = ['/bin/subscription-manager']
        self.valid_rh_keys = ['org', 'activation-key', 'username', 'password',
                              'disable-repo', 'enable-repo', 'add-pool',
                              'rhsm-baseurl', 'server-hostname',
                              'auto-attach', 'service-level']
        self.is_registered = self._is_registered()

    def _verify_keys(self):
        '''
        Checks that the keys in the rh_subscription dict from the user-data
        are what we expect.
        '''

        for k in self.rhel_cfg:
            if k not in self.valid_rh_keys:
                bad_key = "{0} is not a valid key for rh_subscription. "\
                          "Valid keys are: "\
                          "{1}".format(k, ', '.join(self.valid_rh_keys))
                return False, bad_key

        # Check for bad auto-attach value
        if (self.auto_attach is not None) and \
                (str(self.auto_attach).upper() not in ['TRUE', 'FALSE']):
            not_bool = "The key auto-attach must be a value of "\
                       "either True or False"
            return False, not_bool

        if (self.servicelevel is not None) and \
            ((not self.auto_attach) or
                (str(self.auto_attach).upper() == "FALSE")):

            no_auto = "The service-level key must be used in conjunction with "\
                      "the auto-attach key.  Please re-run with auto-attach: "\
                      "True"
            return False, no_auto
        return True, None

    def _is_registered(self):
        '''
        Checks if the system is already registered and returns
        True if so, else False
        '''
        cmd = list(itertools.chain(self.subman, ['identity']))

        if subprocess.call(cmd, stdout=open(os.devnull, 'wb'),
                           stderr=open(os.devnull, 'wb')) == 1:
            return False
        else:
            return True

    def rhn_register(self):
        '''
        Registers the system by userid and password or activation key
        and org.  Returns True when successful False when not.
        '''

        if (self.activation_key is not None) and (self.org is not None):
            # register by activation key
            cmd = list(itertools.chain(self.subman, ['register',
                                       '--activationkey={0}'.
                       format(self.activation_key),
                       '--org={0}'.format(self.org)]))

            # If the baseurl and/or server url are passed in, we register
            # with them.

            if self.rhsm_baseurl is not None:
                cmd.append("--baseurl={0}".format(self.rhsm_baseurl))

            if self.server_hostname is not None:
                cmd.append("--serverurl={0}".format(self.server_hostname))

            return_msg, return_code = self._captureRun(cmd)

            if return_code is not 0:
                self.log.warn("Registration with {0} and {1} failed.".format(
                              self.activation_key, self.org))
                return False

        elif (self.userid is not None) and (self.password is not None):
            # register by username and password
            cmd = list(itertools.chain(self.subman, ['register',
                       '--username={0}'.format(self.userid),
                       '--password={0}'.format(self.password)]))

            # If the baseurl and/or server url are passed in, we register
            # with them.

            if self.rhsm_baseurl is not None:
                cmd.append("--baseurl={0}".format(self.rhsm_baseurl))

            if self.server_hostname is not None:
                cmd.append("--serverurl={0}".format(self.server_hostname))

            # Attempting to register the system only
            return_msg, return_code = self._captureRun(cmd)

            if return_code is not 0:
                # Return message is in a set
                if return_msg[0] == "":
                    self.log.warn("Registration failed")
                    if return_msg[1] is not "":
                        self.log.warn(return_msg[1])
                return False

        else:
            self.log.warn("Unable to register system due to incomplete "
                          "information.")
            self.log.warn("Use either activationkey and org *or* userid "
                          "and password")
            return False

        reg_id = return_msg[0].split("ID: ")[1].rstrip()
        self.log.info("Registered successfully with ID {0}".format(reg_id))
        return True

    def _set_service_level(self):
        cmd = list(itertools.chain(self.subman,
                                   ['attach', '--auto', '--servicelevel={0}'
                                    .format(self.servicelevel)]))

        return_msg, return_code = self._captureRun(cmd)

        if return_code is not 0:
            self.log.warn("Setting the service level failed with: "
                          "{0}".format(return_msg[1].strip()))
            return False
        else:
            for line in return_msg[0].split("\n"):
                if line is not "":
                    self.log.info(line)
            return True

    def _set_auto_attach(self):
        cmd = list(itertools.chain(self.subman, ['attach', '--auto']))
        return_msg, return_code = self._captureRun(cmd)

        if return_code is not 0:
            self.log.warn("Auto-attach failed with: "
                          "{0}]".format(return_msg[1].strip()))
            return False
        else:
            for line in return_msg[0].split("\n"):
                if line is not "":
                    self.log.info(line)
            return True

    def _captureRun(self, cmd):
        '''
        Subprocess command that captures and returns the output and
        return code.
        '''

        r = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        return r.communicate(), r.returncode

    def _getPools(self):
        '''
        Gets the list pools for the active subscription and returns them
        in list form.
        '''
        available = []
        consumed = []

        # Get all available pools
        cmd = list(itertools.chain(self.subman, ['list', '--available',
                                                 '--pool-only']))
        results = subprocess.check_output(cmd)
        available = (results.rstrip()).split("\n")

        # Get all available pools
        cmd = list(itertools.chain(self.subman, ['list', '--consumed',
                                                 '--pool-only']))
        results = subprocess.check_output(cmd)
        consumed = (results.rstrip()).split("\n")
        return available, consumed

    def _getRepos(self):
        '''
        Obtains the current list of active yum repositories and returns
        them in list form.
        '''

        cmd = list(itertools.chain(self.subman, ['repos', '--list-enabled']))
        result, return_code = self._captureRun(cmd)

        active_repos = []
        for repo in result[0].split("\n"):
            if "Repo ID:" in repo:
                active_repos.append((repo.split(':')[1]).strip())

        cmd = list(itertools.chain(self.subman, ['repos', '--list-disabled']))
        result, return_code = self._captureRun(cmd)

        inactive_repos = []
        for repo in result[0].split("\n"):
            if "Repo ID:" in repo:
                inactive_repos.append((repo.split(':')[1]).strip())

        return active_repos, inactive_repos

    def addPool(self, pools):
        '''
        Takes a list of subscription pools and "attaches" them to the
        current subscription
        '''

        # An empty list was passed
        if len(pools) == 0:
            self.log.info("No pools to attach")
            return True

        pool_available, pool_consumed = self._getPools()
        pool_list = []
        cmd = list(itertools.chain(self.subman, ['attach']))
        for pool in pools:
            if (pool not in pool_consumed) and (pool in pool_available):
                pool_list.append('--pool={0}'.format(pool))
            else:
                self.log.warn("Pool {0} is not available".format(pool))
        if len(pool_list) > 0:
            cmd.extend(pool_list)
            try:
                self._captureRun(cmd)
                self.log.info("Attached the following pools to your "
                              "system: %s" % (", ".join(pool_list))
                              .replace('--pool=', ''))
                return True
            except subprocess.CalledProcessError:
                self.log.warn("Unable to attach pool {0}".format(pool))
                return False

    def update_repos(self, erepos, drepos):
        '''
        Takes a list of yum repo ids that need to be disabled or enabled; then
        it verifies if they are already enabled or disabled and finally
        executes the action to disable or enable
        '''

        if (erepos is not None) and (type(erepos) is not list):
            self.log.warn("Repo IDs must in the format of a list.")
            return False

        if (drepos is not None) and (type(drepos) is not list):
            self.log.warn("Repo IDs must in the format of a list.")
            return False

        # Bail if both lists are not populated
        if (len(erepos) == 0) and (len(drepos) == 0):
            self.log.info("No repo IDs to enable or disable")
            return True

        active_repos, inactive_repos = self._getRepos()
        # Creating a list of repoids to be enabled
        enable_list = []
        enable_list_fail = []
        for repoid in erepos:
            if (repoid in inactive_repos):
                enable_list.append("--enable={0}".format(repoid))
            else:
                enable_list_fail.append(repoid)

        # Creating a list of repoids to be disabled
        disable_list = []
        disable_list_fail = []
        for repoid in drepos:
            if repoid in active_repos:
                disable_list.append("--disable={0}".format(repoid))
            else:
                disable_list_fail.append(repoid)

        # Logging any repos that are already enabled or disabled
        if len(enable_list_fail) > 0:
            for fail in enable_list_fail:
                # Check if the repo exists or not
                if fail in active_repos:
                    self.log.info("Repo {0} is already enabled".format(fail))
                else:
                    self.log.warn("Repo {0} does not appear to "
                                  "exist".format(fail))
        if len(disable_list_fail) > 0:
            for fail in disable_list_fail:
                self.log.info("Repo {0} not disabled "
                              "because it is not enabled".format(fail))

        cmd = list(itertools.chain(self.subman, ['repos']))
        if enable_list > 0:
            cmd.extend(enable_list)
        if disable_list > 0:
            cmd.extend(disable_list)

        try:
            return_msg, return_code = self._captureRun(cmd)

        except subprocess.CalledProcessError as e:
            self.log.warn("Unable to alter repos due to {0}".format(e))
            return False

        if enable_list > 0:
            self.log.info("Enabled the following repos: %s" %
                          (", ".join(enable_list)).replace('--enable=', ''))
        if disable_list > 0:
            self.log.info("Disabled the following repos: %s" %
                          (", ".join(disable_list)).replace('--disable=', ''))
        return True
