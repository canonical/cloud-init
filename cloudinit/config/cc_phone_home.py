# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Phone Home
----------
**Summary:** post data to url

This module can be used to post data to a remote host after boot is complete.
If the post url contains the string ``$INSTANCE_ID`` it will be replaced with
the id of the current instance. Either all data can be posted or a list of
keys to post. Available keys are:

    - ``pub_key_dsa``
    - ``pub_key_rsa``
    - ``pub_key_ecdsa``
    - ``instance_id``
    - ``hostname``
    - ``fdqn``

**Internal name:** ``cc_phone_home``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    phone_home:
        url: http://example.com/$INSTANCE_ID/
        post:
            - pub_key_dsa
            - instance_id
            - fqdn
        tries: 10
"""

from cloudinit import templater
from cloudinit import url_helper
from cloudinit import util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

POST_LIST_ALL = [
    'pub_key_dsa',
    'pub_key_rsa',
    'pub_key_ecdsa',
    'instance_id',
    'hostname',
    'fqdn'
]


# phone_home:
#  url: http://my.foo.bar/$INSTANCE/
#  post: all
#  tries: 10
#
# phone_home:
#  url: http://my.foo.bar/$INSTANCE_ID/
#  post: [ pub_key_dsa, pub_key_rsa, pub_key_ecdsa, instance_id, hostname,
#          fqdn ]
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
    except Exception:
        tries = 10
        util.logexc(log, "Configuration entry 'tries' is not an integer, "
                    "using %s instead", tries)

    if post_list == "all":
        post_list = POST_LIST_ALL

    all_keys = {}
    all_keys['instance_id'] = cloud.get_instance_id()
    all_keys['hostname'] = cloud.get_hostname()
    all_keys['fqdn'] = cloud.get_hostname(fqdn=True)

    pubkeys = {
        'pub_key_dsa': '/etc/ssh/ssh_host_dsa_key.pub',
        'pub_key_rsa': '/etc/ssh/ssh_host_rsa_key.pub',
        'pub_key_ecdsa': '/etc/ssh/ssh_host_ecdsa_key.pub',
    }

    for (n, path) in pubkeys.items():
        try:
            all_keys[n] = util.load_file(path)
        except Exception:
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
    for (k, v) in submit_keys.items():
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
        url_helper.read_file_or_url(
            url, data=real_submit_keys, retries=tries, sec_between=3,
            ssl_details=util.fetch_ssl_details(cloud.paths))
    except Exception:
        util.logexc(log, "Failed to post phone home data to %s in %s tries",
                    url, tries)

# vi: ts=4 expandtab
