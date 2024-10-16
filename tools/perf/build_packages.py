#!/usr/bin/env python3
"""Build deb packages"""

import os
import glob
import shutil
import argparse
import tempfile
import logging

from cloudinit import subp


def get_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pathspecs",
        required=True,
        help="Comma-delimited list of pathspecs to build",
    )
    return parser


def build_packages(
    temp_dir: str,
    pathspecs=list[str],
    repo="https://github.com/canonical/cloud-init.git",
):
    debs = []
    repo_dir = f"{temp_dir}/repo/"
    deb_dir = f"{temp_dir}/assets/debs/"
    os.makedirs(deb_dir)
    subp.subp(["git", "clone", repo, repo_dir])
    for pathspec in pathspecs:

        deb_dest = f"{deb_dir}cloud-init-{pathspec}.deb"
        subp.subp(["git", "checkout", pathspec], cwd=repo_dir)
        subp.subp(
            ["./packages/bddeb", "-d"],
            cwd=repo_dir,
            update_env={"DEB_BUILD_OPTIONS": "nocheck"},
        )
        #        subp.subp(["git", "clean", "-fdx"], cwd=repo_dir)
        deb_src = glob.glob(f"{repo_dir}/*bddeb_all.deb")[0]
        shutil.move(deb_src, deb_dest)
        debs.append(deb_dest)
    return debs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("qemu.qmp.protocol").setLevel(logging.WARNING)
    logging.getLogger("pycloudlib").setLevel(logging.INFO)
    logging.getLogger("paramiko.transport:Auth").setLevel(logging.INFO)
    parser = get_parser()
    args = parser.parse_args()
    temp_dir = tempfile.TemporaryDirectory(delete=False)
    print(build_packages(temp_dir.name, args.pathspecs.split(",")))
