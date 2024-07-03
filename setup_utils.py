import os
import subprocess
import sys
from typing import List


def is_f(p: str) -> bool:
    return os.path.isfile(p)


def is_generator(p: str) -> bool:
    return "-generator" in p


def pkg_config_read(library: str, var: str) -> str:
    fallbacks = {
        "systemd": {
            "systemdsystemconfdir": "/etc/systemd/system",
            "systemdsystemunitdir": "/lib/systemd/system",
            "systemdsystemgeneratordir": "/lib/systemd/system-generators",
        },
        "udev": {
            "udevdir": "/lib/udev",
        },
    }
    cmd = ["pkg-config", f"--variable={var}", library]
    try:
        path = subprocess.check_output(cmd).decode("utf-8")  # nosec B603
        path = path.strip()
    except Exception:
        path = fallbacks[library][var]
    if path.startswith("/"):
        path = path[1:]

    return path


def version_to_pep440(version: str) -> str:
    # read-version can spit out something like 22.4-15-g7f97aee24
    # which is invalid under PEP 440. If we replace the first - with a +
    # that should give us a valid version.
    return version.replace("-", "+", 1)


def get_version() -> str:
    cmd = [sys.executable, "tools/read-version"]
    ver = subprocess.check_output(cmd)  # B603
    version = ver.decode("utf-8").strip()
    return version_to_pep440(version)


def read_requires() -> List[str]:
    cmd = [sys.executable, "tools/read-dependencies"]
    deps = subprocess.check_output(cmd)  # nosec B603
    return deps.decode("utf-8").splitlines()
