# This file is part of cloud-init. See LICENSE file for license information.

import glob
import os
import random
import string
import tempfile
import yaml

from cloudinit.distros import OSFAMILIES
from cloudinit import util as c_util
from tests.cloud_tests import LOG


def list_test_data(data_dir):
    """
    find all tests with test data available in data_dir
    data_dir should contain <platforms>/<os_name>/<testnames>/<data>
    return_value: {<platform>: {<os_name>: [<testname>]}}
    """
    if not os.path.isdir(data_dir):
        raise ValueError("bad data dir")

    res = {}
    for platform in os.listdir(data_dir):
        res[platform] = {}
        for os_name in os.listdir(os.path.join(data_dir, platform)):
            res[platform][os_name] = [
                os.path.sep.join(f.split(os.path.sep)[-2:]) for f in
                glob.glob(os.sep.join((data_dir, platform, os_name, '*/*')))]

    LOG.debug('found test data: %s\n', res)
    return res


def gen_instance_name(prefix='cloud-test', image_desc=None, use_desc=None,
                      max_len=63, delim='-', max_tries=16, used_list=None,
                      valid=string.ascii_lowercase + string.digits):
    """
    generate an unique name for a test instance
    prefix: name prefix, defaults to cloud-test, default should be left
    image_desc: short string with image desc, will be truncated to 16 chars
    use_desc: short string with usage desc, will be truncated to 30 chars
    max_len: maximum name length, defaults to 64 chars
    delim: delimiter to use between tokens
    max_tries: maximum tries to find a unique name before giving up
    used_list: already used names, or none to not check
    valid: string of valid characters for name
    return_value: valid, unused name, may raise StopIteration
    """
    unknown = 'unknown'

    def join(*args):
        """
        join args with delim
        """
        return delim.join(args)

    def fill(*args):
        """
        join name elems and fill rest with random data
        """
        name = join(*args)
        num = max_len - len(name) - len(delim)
        return join(name, ''.join(random.choice(valid) for _ in range(num)))

    def clean(elem, max_len):
        """
        filter bad characters out of elem and trim to length
        """
        elem = elem[:max_len] if elem else unknown
        return ''.join(c if c in valid else delim for c in elem)

    return next(name for name in
                (fill(prefix, clean(image_desc, 16), clean(use_desc, 30))
                 for _ in range(max_tries))
                if not used_list or name not in used_list)


def sorted_unique(iterable, key=None, reverse=False):
    """
    return_value: a sorted list of unique items in iterable
    """
    return sorted(set(iterable), key=key, reverse=reverse)


def get_os_family(os_name):
    """
    get os family type for os_name
    """
    return next((k for k, v in OSFAMILIES.items() if os_name in v), None)


def current_verbosity():
    """
    get verbosity currently in effect from log level
    return_value: verbosity, 0-2, 2 = verbose, 0 = quiet
    """
    return max(min(3 - int(LOG.level / 10), 2), 0)


def is_writable_dir(path):
    """
    make sure dir is writable
    """
    try:
        c_util.ensure_dir(path)
        os.remove(tempfile.mkstemp(dir=os.path.abspath(path))[1])
    except (IOError, OSError):
        return False
    return True


def is_clean_writable_dir(path):
    """
    make sure dir is empty and writable, creating it if it does not exist
    return_value: True/False if successful
    """
    path = os.path.abspath(path)
    if not (is_writable_dir(path) and len(os.listdir(path)) == 0):
        return False
    return True


def configure_yaml():
    yaml.add_representer(str, (lambda dumper, data: dumper.represent_scalar(
        'tag:yaml.org,2002:str', data, style='|' if '\n' in data else '')))


def yaml_format(data):
    """
    format data as yaml
    """
    configure_yaml()
    return yaml.dump(data, indent=2, default_flow_style=False)


def yaml_dump(data, path):
    """
    dump data to path in yaml format
    """
    write_file(os.path.abspath(path), yaml_format(data), omode='w')


def merge_results(data, path):
    """
    handle merging results from collect phase and verify phase
    """
    current = {}
    if os.path.exists(path):
        with open(path, 'r') as fp:
            current = c_util.load_yaml(fp.read())
    current.update(data)
    yaml_dump(current, path)


def write_file(*args, **kwargs):
    """
    write a file using cloudinit.util.write_file
    """
    c_util.write_file(*args, **kwargs)

# vi: ts=4 expandtab
