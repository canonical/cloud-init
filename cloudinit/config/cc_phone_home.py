# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Phone Home: Post data to url"""

import logging

from cloudinit import templater, url_helper, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

POST_LIST_ALL = [
    "pub_key_rsa",
    "pub_key_ecdsa",
    "pub_key_ed25519",
    "instance_id",
    "hostname",
    "fqdn",
]

meta: MetaSchema = {
    "id": "cc_phone_home",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["phone_home"],
}  # type: ignore

LOG = logging.getLogger(__name__)
# phone_home:
#  url: http://my.foo.bar/$INSTANCE/
#  post: all
#  tries: 10
#
# phone_home:
#  url: http://my.foo.bar/$INSTANCE_ID/
#  post: [ pub_key_rsa, pub_key_ecdsa, instance_id, hostname,
#          fqdn ]
#


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if len(args) != 0:
        ph_cfg = util.read_conf(args[0])
    else:
        if "phone_home" not in cfg:
            LOG.debug(
                "Skipping module named %s, "
                "no 'phone_home' configuration found",
                name,
            )
            return
        ph_cfg = cfg["phone_home"]

    if "url" not in ph_cfg:
        LOG.warning(
            "Skipping module named %s, "
            "no 'url' found in 'phone_home' configuration",
            name,
        )
        return

    url = ph_cfg["url"]
    post_list = ph_cfg.get("post", "all")
    tries = ph_cfg.get("tries")
    try:
        tries = int(tries)  # type: ignore
    except (ValueError, TypeError):
        tries = 10
        util.logexc(
            LOG,
            "Configuration entry 'tries' is not an integer, using %s instead",
            tries,
        )

    if post_list == "all":
        post_list = POST_LIST_ALL

    all_keys = {
        "instance_id": cloud.get_instance_id(),
        "hostname": cloud.get_hostname().hostname,
        "fqdn": cloud.get_hostname(fqdn=True).hostname,
    }

    pubkeys = {
        "pub_key_rsa": "/etc/ssh/ssh_host_rsa_key.pub",
        "pub_key_ecdsa": "/etc/ssh/ssh_host_ecdsa_key.pub",
        "pub_key_ed25519": "/etc/ssh/ssh_host_ed25519_key.pub",
    }

    for (n, path) in pubkeys.items():
        try:
            all_keys[n] = util.load_text_file(path)
        except Exception:
            util.logexc(
                LOG, "%s: failed to open, can not phone home that data!", path
            )

    submit_keys = {}
    for k in post_list:
        if k in all_keys:
            submit_keys[k] = all_keys[k]
        else:
            submit_keys[k] = None
            LOG.warning(
                "Requested key %s from 'post'"
                " configuration list not available",
                k,
            )

    # Get them read to be posted
    real_submit_keys = {}
    for (k, v) in submit_keys.items():
        if v is None:
            real_submit_keys[k] = "N/A"
        else:
            real_submit_keys[k] = str(v)

    # Incase the url is parameterized
    url_params = {
        "INSTANCE_ID": all_keys["instance_id"],
    }
    url = templater.render_string(url, url_params)
    try:
        url_helper.read_file_or_url(
            url,
            data=real_submit_keys,
            retries=tries - 1,
            sec_between=3,
            ssl_details=util.fetch_ssl_details(cloud.paths),
        )
    except Exception:
        util.logexc(
            LOG, "Failed to post phone home data to %s in %s tries", url, tries
        )
