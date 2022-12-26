"""HttpScripts Module: Run scripts fetched by http"""
import subprocess
import sys
import urllib.request
from logging import Logger, getLogger
from subprocess import PIPE, STDOUT, CalledProcessError
from textwrap import dedent
from typing import List

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
This module is like ``curl http://example.com/install.sh | sh``
"""

meta: MetaSchema = {
    "id": "cc_http_scripts",
    "name": "HttpScripts",
    "title": "run scripts fetched by http",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["http_scripts"],
    "examples": [
        dedent(
            """\
            http_scripts:
              - url: http://example.com/install.sh
                environments:
                  ENV: val
            """
        )
    ],
}

__doc__ = get_meta_doc(meta)
LOG = getLogger(__name__)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    http_scripts: List[dict] = cfg.get("http_scripts", [])
    for http_script in http_scripts:
        if "url" not in http_script:
            raise ValueError(f"Missing required key 'url' from {http_script}")

        url = http_script.get("url", "")
        environments = http_script.get("environments", {})

        LOG.debug("fetch script: %s", url)
        script = fetch_script(url)

        LOG.debug("run script: %s", url)
        p = subprocess.run(
            ["/bin/sh"],
            input=script,
            stdout=PIPE,
            stderr=STDOUT,
            env=environments,
            check=True,
        )

        if p.stdout:
            sys.stdout.write(f"{p.stdout!r}")


def fetch_script(url: str) -> bytes:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as res:
        return res.read()
