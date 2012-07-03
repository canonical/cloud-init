#!/usr/bin/python

# Provides a somewhat random, somewhat compat, somewhat useful mock version of
#
# http://docs.amazonwebservices.com/AWSEC2/2007-08-29/DeveloperGuide/AESDG-chapter-instancedata.html

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

# Constants
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
    'latest',
]

BLOCK_DEVS = [
    'ami',
    'root',
    'ephemeral0',
]

DEV_PREFIX = 'v'
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
    'reservation-id',
    'security-groups'
]

INSTANCE_TYPES = [
    'm1.small',
    'm1.medium',
    'm1.large',
    'm1.xlarge',
]

AVAILABILITY_ZONES = [
    "us-east-1a",
    "us-east-1b",
    "us-east-1c",
    'us-west-1',
    "us-east-1d",
    'eu-west-1a',
    'eu-west-1b',
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


ID_CHARS = [c for c in (string.ascii_uppercase + string.digits)]
def id_generator(size=6, lower=False):
    txt = ''.join(random.choice(ID_CHARS) for x in range(size))
    if lower:
        return txt.lower()
    else:
        return txt


class MetaDataHandler(object):

    def __init__(self, opts):
        self.opts = opts
        self.instances = {}

    def get_data(self, params, who, **kwargs):
        if not params:
            caps = sorted(META_CAPABILITIES)
            return "\n".join(caps)
        action = params[0]
        action = action.lower()
        if action == 'instance-id':
            return 'i-%s' % (id_generator(lower=True))
        elif action == 'ami-launch-index':
            return "%s" % random.choice([0,1,2,3])
        elif action == 'aki-id':
            return 'aki-%s' % (id_generator(lower=True))
        elif action == 'ami-id':
            return 'ami-%s' % (id_generator(lower=True))
        elif action == 'ari-id':
            return 'ari-%s' % (id_generator(lower=True))
        elif action == 'block-device-mapping':
            nparams = params[1:]
            if not nparams:
                devs = sorted(BLOCK_DEVS)
                return "\n".join(devs)
            else:
                return "%s" % (DEV_MAPPINGS.get(nparams[0].strip(), ''))
        elif action in ['hostname', 'local-hostname', 'public-hostname']:
            return "%s" % (who)
        elif action == 'instance-type':
            return random.choice(INSTANCE_TYPES)
        elif action == 'ami-manifest-path':
            return 'my-amis/spamd-image.manifest.xml'
        elif action == 'security-groups':
            return 'default'
        elif action in ['local-ipv4', 'public-ipv4']:
            there_ip = kwargs.get('client_ip', '10.0.0.1')
            return "%s" % (there_ip)
        elif action == 'reservation-id':
            return "r-%s" % (id_generator(lower=True))
        elif action == 'product-codes':
            return "%s" % (id_generator(size=8))
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
        if self.opts['user_data_file']:
            with open(opts['user_data_file'], 'rb') as fh:
                blob = fh.read()
                blob = blob.strip()
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
        versions = []
        for v in EC2_VERSIONS:
            if v == 'latest':
                continue
            else:
                versions.append(v)
        versions = sorted(versions)
        return "\n".join(versions)

    def log_message(self, format, *args):
        msg = "%s - %s" % (self.address_string(), format % (args))
        log.info(msg)

    def _find_method(self, path):
        # Puke! (globals)
        global meta_fetcher
        global user_fetcher
        func_mapping = {
            'user-data': user_fetcher.get_data,
            'meta-data': meta_fetcher.get_data,
        }
        segments = [piece for piece in path.split('/') if len(piece)]
        if not segments:
            return self._get_versions
        date = segments[0].strip().lower()
        if date not in EC2_VERSIONS:
            raise WebException(httplib.BAD_REQUEST, "Unknown date format %r" % date)
        if len(segments) < 2:
            raise WebException(httplib.BAD_REQUEST, "No action provided")
        look_name = segments[1].lower()
        if look_name not in func_mapping:
            raise WebException(httplib.BAD_REQUEST, "Unknown requested data %r" % look_name)
        base_func = func_mapping[look_name]
        who = self.address_string()
        kwargs = {
            'params': list(segments[2:]),
            'who': self.address_string(),
            'client_ip': self.client_address[0],
        }
        return functools.partial(base_func, **kwargs)

    def _do_response(self):
        who = self.client_address
        log.info("Got a call from %s for path %s", who, self.path)
        try:
            func = self._find_method(self.path)
            log.info("Calling into func %s to get your data.", func)
            data = func()
            if not data:
                data = ''
            self.send_response(httplib.OK)
            self.send_header("Content-Type", "binary/octet-stream")
            self.send_header("Content-Length", len(data))
            log.info("Sending data (len=%s):\n%s", len(data), format_text(data))
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


def setup_logging(log_level, format='%(levelname)s: @%(name)s : %(message)s'):
    root_logger = logging.getLogger()
    console_logger = logging.StreamHandler(sys.stdout)
    console_logger.setFormatter(logging.Formatter(format))
    root_logger.addHandler(console_logger)
    root_logger.setLevel(log_level)


def extract_opts():
    parser = OptionParser()
    parser.add_option("-p", "--port", dest="port", action="store", type=int, default=80,
                  help="port from which to serve traffic (default: %default)", metavar="PORT")
    parser.add_option("-f", '--user-data-file', dest='user_data_file', action='store',
                      help="user data filename to serve back to incoming requests", metavar='FILE')
    (options, args) = parser.parse_args()
    out = dict()
    out['extra'] = args
    out['port'] = options.port
    out['user_data_file'] = None
    if options.user_data_file:
        if not os.path.isfile(options.user_data_file):
            parser.error("Option -f specified a non-existent file")
        out['user_data_file'] = options.user_data_file
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
    server = HTTPServer(('0.0.0.0', opts['port']), Ec2Handler)
    sa = server.socket.getsockname()
    log.info("Serving server on %s using port %s ...", sa[0], sa[1])
    server.serve_forever()


if __name__ == '__main__':
    run_server()
