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

from cloudinit.settings import PER_INSTANCE
from cloudinit import util, subp

frequency = PER_INSTANCE

LSPATH = '/usr/sbin/lspath'
CHDEV = '/usr/sbin/chdev'

DEFAULT_INTERVAL = 60


def handle(name, _cfg, _cloud, log, _args):
    hcheck_interval = util.get_cfg_option_str(_cfg,
                                              'multipath_hcheck_interval',
                                              default=DEFAULT_INTERVAL)
    try:
        hcheck_interval = int(hcheck_interval)
    except ValueError:
        log.warn('The hcheck interval for multipath specified in the '
                 'cloud.cfg file, "%s", could not be converted to an integer. '
                 'Ensure that the interval is specified as an integer. '
                 'The default interval of %d seconds is being used.' %
                 (hcheck_interval, DEFAULT_INTERVAL))
        hcheck_interval = DEFAULT_INTERVAL

    log.debug('Attempting to set the multipath hcheck interval to %d' %
              hcheck_interval)

    hdisks = []
    try:
        hdisks = subp.subp([LSPATH, '-F', 'name'])[0].strip().split('\n')
        hdisks = set(hdisks)
    except subp.ProcessExecutionError:
        util.logexc(log, 'Failed to get paths to multipath device.')
        raise

    if len(hdisks) < 1:
        raise Exception('Failed to find any paths to multipath device.')

    # Permanently change the hcheck interval for each disk
    for hdisk in hdisks:
        try:
            env = os.environ
            env['LANG'] = 'C'
            out = subp.subp([CHDEV, '-l', hdisk, '-a',
                             'hcheck_interval=%d' % hcheck_interval, '-P'],
                            env=env)[0]
            log.debug(out)
        except subp.ProcessExecutionError:
            util.logexc(log, 'Failed to permanently change the hcheck '
                        'interval for hdisk "%s".' % hdisk)
            raise
