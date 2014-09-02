# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#    Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

from cloudinit import templater
from cloudinit import util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

POST_LIST_ALL = [
    'pub_key_dsa',
    'pub_key_rsa',
    'pub_key_ecdsa',
    'instance_id',
    'hostname'
]


# phone_home:
#  url: http://my.foo.bar/$INSTANCE/
#  post: all
#  tries: 10
#
# phone_home:
#  url: http://my.foo.bar/$INSTANCE_ID/
#  post: [ pub_key_dsa, pub_key_rsa, pub_key_ecdsa, instance_id
#
def handle(name, cfg, cloud, log, args):
    if len(args) != 0:
        ph_cfg = util.read_conf(args[0])
    else:
        if 'phone_home' not in cfg:
            log.debug(("Skipping module named %s, "
                       "no 'phone_home' configuration found"), name)
            return
        ph_cfg = cfg['phone_home']

    if 'url' not in ph_cfg:
        log.warn(("Skipping module named %s, "
                  "no 'url' found in 'phone_home' configuration"), name)
        return

    url = ph_cfg['url']
    post_list = ph_cfg.get('post', 'all')
    tries = ph_cfg.get('tries')
    try:
        tries = int(tries)
    except:
        tries = 10
        util.logexc(log, "Configuration entry 'tries' is not an integer, "
                    "using %s instead", tries)

    if post_list == "all":
        post_list = POST_LIST_ALL

    all_keys = {}
    all_keys['instance_id'] = cloud.get_instance_id()
    all_keys['hostname'] = cloud.get_hostname()

    pubkeys = {
        'pub_key_dsa': '/etc/ssh/ssh_host_dsa_key.pub',
        'pub_key_rsa': '/etc/ssh/ssh_host_rsa_key.pub',
        'pub_key_ecdsa': '/etc/ssh/ssh_host_ecdsa_key.pub',
    }

    for (n, path) in pubkeys.iteritems():
        try:
            all_keys[n] = util.load_file(path)
        except:
            util.logexc(log, "%s: failed to open, can not phone home that "
                        "data!", path)

    submit_keys = {}
    for k in post_list:
        if k in all_keys:
            submit_keys[k] = all_keys[k]
        else:
            submit_keys[k] = None
            log.warn(("Requested key %s from 'post'"
                      " configuration list not available"), k)

    # Get them read to be posted
    real_submit_keys = {}
    for (k, v) in submit_keys.iteritems():
        if v is None:
            real_submit_keys[k] = 'N/A'
        else:
            real_submit_keys[k] = str(v)

    # Incase the url is parameterized
    url_params = {
        'INSTANCE_ID': all_keys['instance_id'],
    }
    url = templater.render_string(url, url_params)
    try:
        util.read_file_or_url(url, data=real_submit_keys,
                              retries=tries, sec_between=3,
                              ssl_details=util.fetch_ssl_details(cloud.paths))
    except:
        util.logexc(log, "Failed to post phone home data to %s in %s tries",
                    url, tries)
