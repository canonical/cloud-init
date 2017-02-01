#!/usr/bin/python

# Provides a somewhat random, somewhat compat, somewhat useful mock version of
# http://docs.amazonwebservices.com
#   /AWSEC2/2007-08-29/DeveloperGuide/AESDG-chapter-instancedata.htm

"""
To use this to mimic the EC2 metadata service entirely, run it like:
  # Where 'eth0' is *some* interface.
  sudo ifconfig eth0:0 169.254.169.254 netmask 255.255.255.255

  sudo ./mock-meta.py -a 169.254.169.254 -p 80

Then:
  wget -q http://169.254.169.254/latest/meta-data/instance-id -O -; echo
  curl --silent http://169.254.169.254/latest/meta-data/instance-id ; echo
  ec2metadata --instance-id
"""

import functools
import httplib
import json
import logging
import os
import random
import string
import sys
import yaml

from optparse import OptionParser

from BaseHTTPServer import (HTTPServer, BaseHTTPRequestHandler)

log = logging.getLogger('meta-server')

EC2_VERSIONS = [
    '1.0',
    '2007-01-19',
    '2007-03-01',
    '2007-08-29',
    '2007-10-10',
    '2007-12-15',
    '2008-02-01',
    '2008-09-01',
    '2009-04-04',
]

BLOCK_DEVS = [
    'ami',
    'ephemeral0',
    'root',
]

DEV_PREFIX = 'v'  # This seems to vary alot depending on images...
DEV_MAPPINGS = {
    'ephemeral0': '%sda2' % (DEV_PREFIX),
    'root': '/dev/%sda1' % (DEV_PREFIX),
    'ami': '%sda1' % (DEV_PREFIX),
    'swap': '%sda3' % (DEV_PREFIX),
}

META_CAPABILITIES = [
    'aki-id',
    'ami-id',
    'ami-launch-index',
    'ami-manifest-path',
    'ari-id',
    'block-device-mapping/',
    'hostname',
    'instance-action',
    'instance-id',
    'instance-type',
    'local-hostname',
    'local-ipv4',
    'placement/',
    'product-codes',
    'public-hostname',
    'public-ipv4',
    'public-keys/',
    'reservation-id',
    'security-groups'
]

PUB_KEYS = {
    'brickies': [
        ('ssh-rsa '
         'AAAAB3NzaC1yc2EAAAABIwAAAQEA3I7VUf2l5gSn5uavROsc5HRDpZdQueUq5ozemN'
         'Sj8T7enqKHOEaFoU2VoPgGEWC9RyzSQVeyD6s7APMcE82EtmW4skVEgEGSbDc1pvxz'
         'xtchBj78hJP6Cf5TCMFSXw+Fz5rF1dR23QDbN1mkHs7adr8GW4kSWqU7Q7NDwfIrJJ'
         'tO7Hi42GyXtvEONHbiRPOe8stqUly7MvUoN+5kfjBM8Qqpfl2+FNhTYWpMfYdPUnE7'
         'u536WqzFmsaqJctz3gBxH9Ex7dFtrxR4qiqEr9Qtlu3xGn7Bw07/+i1D+ey3ONkZLN'
         '+LQ714cgj8fRS4Hj29SCmXp5Kt5/82cD/VN3NtHw== brickies'),
        '',
    ],
}

INSTANCE_TYPES = [
    'm1.large',
    'm1.medium',
    'm1.small',
    'm1.xlarge',
]

AVAILABILITY_ZONES = [
    "us-east-1a",
    "us-east-1b",
    "us-east-1c",
    "us-east-1d",
    'eu-west-1a',
    'eu-west-1b',
    'us-west-1',
]

PLACEMENT_CAPABILITIES = {
    'availability-zone': AVAILABILITY_ZONES,
}

NOT_IMPL_RESPONSE = json.dumps({})


class WebException(Exception):
    def __init__(self, code, msg):
        Exception.__init__(self, msg)
        self.code = code


def yamlify(data):
    formatted = yaml.dump(data,
                          line_break="\n",
                          indent=4,
                          explicit_start=True,
                          explicit_end=True,
                          default_flow_style=False)
    return formatted


def format_text(text):
    if not len(text):
        return "<<"
    lines = text.splitlines()
    nlines = []
    for line in lines:
        nlines.append("<< %s" % line)
    return "\n".join(nlines)


def traverse(keys, mp):
    result = dict(mp)
    for k in keys:
        try:
            result = result.get(k)
        except (AttributeError, TypeError):
            result = None
            break
    return result


ID_CHARS = [c for c in (string.ascii_uppercase + string.digits)]


def id_generator(size=6, lower=False):
    txt = ''.join(random.choice(ID_CHARS) for x in range(size))
    if lower:
        return txt.lower()
    else:
        return txt


def get_ssh_keys():
    keys = {}
    keys.update(PUB_KEYS)

    # Nice helper to add in the 'running' users key (if they have one)
    key_pth = os.path.expanduser('~/.ssh/id_rsa.pub')
    if not os.path.isfile(key_pth):
        key_pth = os.path.expanduser('~/.ssh/id_dsa.pub')

    if os.path.isfile(key_pth):
        with open(key_pth, 'rb') as fh:
            contents = fh.read()
        keys[os.getlogin()] = [contents, '']

    return keys


class MetaDataHandler(object):

    def __init__(self, opts):
        self.opts = opts
        self.instances = {}

    def get_data(self, params, who, **kwargs):
        if not params:
            # Show the root level capabilities when
            # no params are passed...
            caps = sorted(META_CAPABILITIES)
            return "\n".join(caps)
        action = params[0]
        action = action.lower()
        if action == 'instance-id':
            return 'i-%s' % (id_generator(lower=True))
        elif action == 'ami-launch-index':
            return "%s" % random.choice([0, 1, 2, 3])
        elif action == 'aki-id':
            return 'aki-%s' % (id_generator(lower=True))
        elif action == 'ami-id':
            return 'ami-%s' % (id_generator(lower=True))
        elif action == 'ari-id':
            return 'ari-%s' % (id_generator(lower=True))
        elif action == 'block-device-mapping':
            nparams = params[1:]
            if not nparams:
                return "\n".join(BLOCK_DEVS)
            else:
                subvalue = traverse(nparams, DEV_MAPPINGS)
                if not subvalue:
                    return "\n".join(sorted(list(DEV_MAPPINGS.keys())))
                else:
                    return str(subvalue)
        elif action in ['hostname', 'local-hostname', 'public-hostname']:
            # Just echo back there own hostname that they called in on..
            return "%s" % (who)
        elif action == 'instance-type':
            return random.choice(INSTANCE_TYPES)
        elif action == 'ami-manifest-path':
            return 'my-amis/spamd-image.manifest.xml'
        elif action == 'security-groups':
            return 'default'
        elif action in ['local-ipv4', 'public-ipv4']:
            # Just echo back there own ip that they called in on...
            return "%s" % (kwargs.get('client_ip', '10.0.0.1'))
        elif action == 'reservation-id':
            return "r-%s" % (id_generator(lower=True))
        elif action == 'product-codes':
            return "%s" % (id_generator(size=8))
        elif action == 'public-keys':
            nparams = params[1:]
            # This is a weird kludge, why amazon why!!!
            # public-keys is messed up, list of /latest/meta-data/public-keys/
            # shows something like: '0=brickies'
            # but a GET to /latest/meta-data/public-keys/0=brickies will fail
            # you have to know to get '/latest/meta-data/public-keys/0', then
            # from there you get a 'openssh-key', which you can get.
            # this hunk of code just re-works the object for that.
            avail_keys = get_ssh_keys()
            key_ids = sorted(list(avail_keys.keys()))
            if nparams:
                mybe_key = nparams[0]
                try:
                    key_id = int(mybe_key)
                    key_name = key_ids[key_id]
                except:
                    raise WebException(httplib.BAD_REQUEST,
                                       "Unknown key id %r" % mybe_key)
                # Extract the possible sub-params
                result = traverse(nparams[1:], {
                    "openssh-key": "\n".join(avail_keys[key_name]),
                })
                if isinstance(result, (dict)):
                    # TODO(harlowja): This might not be right??
                    result = "\n".join(sorted(result.keys()))
                if not result:
                    result = ''
                return result
            else:
                contents = []
                for (i, key_id) in enumerate(key_ids):
                    contents.append("%s=%s" % (i, key_id))
                return "\n".join(contents)
        elif action == 'placement':
            nparams = params[1:]
            if not nparams:
                pcaps = sorted(PLACEMENT_CAPABILITIES.keys())
                return "\n".join(pcaps)
            else:
                pentry = nparams[0].strip().lower()
                if pentry == 'availability-zone':
                    zones = PLACEMENT_CAPABILITIES[pentry]
                    return "%s" % random.choice(zones)
                else:
                    return "%s" % (PLACEMENT_CAPABILITIES.get(pentry, ''))
        else:
            log.warn(("Did not implement action %s, "
                      "returning empty response: %r"),
                     action, NOT_IMPL_RESPONSE)
            return NOT_IMPL_RESPONSE


class UserDataHandler(object):

    def __init__(self, opts):
        self.opts = opts

    def _get_user_blob(self, **kwargs):
        blob = None
        if self.opts['user_data_file'] is not None:
            blob = self.opts['user_data_file']
        if not blob:
            blob_mp = {
                'hostname': kwargs.get('who', 'localhost'),
            }
            lines = [
                "#cloud-config",
                yamlify(blob_mp),
            ]
            blob = "\n".join(lines)
        return blob.strip()

    def get_data(self, params, who, **kwargs):
        if not params:
            return self._get_user_blob(who=who)
        return NOT_IMPL_RESPONSE


# Seem to need to use globals since can't pass
# data into the request handlers instances...
# Puke!
meta_fetcher = None
user_fetcher = None


class Ec2Handler(BaseHTTPRequestHandler):

    def _get_versions(self):
        versions = ['latest'] + EC2_VERSIONS
        versions = sorted(versions)
        return "\n".join(versions)

    def log_message(self, fmt, *args):
        msg = "%s - %s" % (self.address_string(), fmt % (args))
        log.info(msg)

    def _find_method(self, path):
        # Puke! (globals)
        func_mapping = {
            'user-data': user_fetcher.get_data,
            'meta-data': meta_fetcher.get_data,
        }
        segments = [piece for piece in path.split('/') if len(piece)]
        log.info("Received segments %s", segments)
        if not segments:
            return self._get_versions
        date = segments[0].strip().lower()
        if date not in self._get_versions():
            raise WebException(httplib.BAD_REQUEST,
                               "Unknown version format %r" % date)
        if len(segments) < 2:
            raise WebException(httplib.BAD_REQUEST, "No action provided")
        look_name = segments[1].lower()
        if look_name not in func_mapping:
            raise WebException(httplib.BAD_REQUEST,
                               "Unknown requested data %r" % look_name)
        base_func = func_mapping[look_name]
        who = self.address_string()
        ip_from = self.client_address[0]
        if who == ip_from:
            # Nothing resolved, so just use 'localhost'
            who = 'localhost'
        kwargs = {
            'params': list(segments[2:]),
            'who': who,
            'client_ip': ip_from,
        }
        return functools.partial(base_func, **kwargs)

    def _do_response(self):
        who = self.client_address
        log.info("Got a call from %s for path %s", who, self.path)
        try:
            func = self._find_method(self.path)
            data = func()
            if not data:
                data = ''
            self.send_response(httplib.OK)
            self.send_header("Content-Type", "binary/octet-stream")
            self.send_header("Content-Length", len(data))
            log.info("Sending data (len=%s):\n%s", len(data),
                     format_text(data))
            self.end_headers()
            self.wfile.write(data)
        except RuntimeError as e:
            log.exception("Error somewhere in the server.")
            self.send_error(httplib.INTERNAL_SERVER_ERROR, message=str(e))
        except WebException as e:
            code = e.code
            log.exception(str(e))
            self.send_error(code, message=str(e))

    def do_GET(self):
        self._do_response()

    def do_POST(self):
        self._do_response()


def setup_logging(log_level, fmt='%(levelname)s: @%(name)s : %(message)s'):
    root_logger = logging.getLogger()
    console_logger = logging.StreamHandler(sys.stdout)
    console_logger.setFormatter(logging.Formatter(fmt))
    root_logger.addHandler(console_logger)
    root_logger.setLevel(log_level)


def extract_opts():
    parser = OptionParser()
    parser.add_option("-p", "--port", dest="port", action="store", type=int,
                      default=80, metavar="PORT",
                      help=("port from which to serve traffic"
                            " (default: %default)"))
    parser.add_option("-a", "--addr", dest="address", action="store", type=str,
                      default='0.0.0.0', metavar="ADDRESS",
                      help=("address from which to serve traffic"
                            " (default: %default)"))
    parser.add_option("-f", '--user-data-file', dest='user_data_file',
                      action='store', metavar='FILE',
                      help=("user data filename to serve back to"
                            "incoming requests"))
    (options, args) = parser.parse_args()
    out = dict()
    out['extra'] = args
    out['port'] = options.port
    out['user_data_file'] = None
    out['address'] = options.address
    if options.user_data_file:
        if not os.path.isfile(options.user_data_file):
            parser.error("Option -f specified a non-existent file")
        with open(options.user_data_file, 'rb') as fh:
            out['user_data_file'] = fh.read()
    return out


def setup_fetchers(opts):
    global meta_fetcher
    global user_fetcher
    meta_fetcher = MetaDataHandler(opts)
    user_fetcher = UserDataHandler(opts)


def run_server():
    # Using global here since it doesn't seem like we
    # can pass opts into a request handler constructor...
    opts = extract_opts()
    setup_logging(logging.DEBUG)
    setup_fetchers(opts)
    log.info("CLI opts: %s", opts)
    server_address = (opts['address'], opts['port'])
    server = HTTPServer(server_address, Ec2Handler)
    sa = server.socket.getsockname()
    log.info("Serving ec2 metadata on %s using port %s ...", sa[0], sa[1])
    server.serve_forever()


if __name__ == '__main__':
    run_server()

# vi: ts=4 expandtab
