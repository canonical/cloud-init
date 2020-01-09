# This file is part of cloud-init. See LICENSE file for license information.

""" Run cloud-init in daemon mode. """

import argparse
import contextlib
import json
import os
import socket
import sys

from cloudinit.cmd.main import main as cimain
from cloudinit import log as cilog

NAME = 'daemon'
CI_SOCKET = "/run/cloud-init/unix.socket"


@contextlib.contextmanager
def DomainServer(addr):
    sock = None
    try:
        basedir = os.path.dirname(addr)
        if not os.path.exists(basedir):
            os.makedirs(basedir)
        if os.path.exists(addr):
            os.unlink(addr)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(addr)
        sock.listen(10)
        yield sock
    finally:
        if sock:
            sock.close()
        if os.path.exists(addr):
            os.unlink(addr)


def log(stream, msg):
    stream.write(msg + '\n')
    stream.flush()


def info(msg):
    log(sys.stdout, "INFO: " + str(msg))


def error(msg):
    log(sys.stderr, "ERROR: " + str(msg))


def handle_args(name, args):
    with DomainServer(CI_SOCKET) as sock:
        expected = set(['local', 'net', 'modules', 'final'])
        completed = set()
        while completed != expected:
            conn, _ = sock.accept()
            data = conn.recv(1024)
            try:
                message = json.loads(data.decode('utf-8'))
            except Exception as e:
                error(e)
                message = None
            if message:
                command = message.get('command')
                if not command:
                    continue
                if command == 'local':
                    stage = 'local'
                    sysv_args = ['cloud-init', 'init', '--local']
                elif command == 'net':
                    stage = 'net'
                    sysv_args = ['cloud-init', 'init']
                elif command == 'modules':
                    stage = 'modules'
                    sysv_args = ['cloud-init', 'modules', '--mode=config']
                elif command == 'final':
                    stage = 'final'
                    sysv_args = ['cloud-init', 'modules', '--mode=final']

                try:
                    cimain(sysv_args=sysv_args)
                    # reset logging between stages
                    cilog.resetLogging()
                except Exception:
                    pass
                completed.add(stage)

            conn.close()
        info('Cloud-init daemon exiting')
    return 0


def get_parser(parser=None):
    if not parser:
        parser = argparse.ArgumentParser(
            prog=NAME,
            description='Run cloud-init in daemon mode')
    return parser


def main():
    """Run cloud-init in daemon mode."""
    parser = get_parser()
    sys.exit(handle_args(NAME, parser.parse_args()))


if __name__ == '__main__':
    main()


# vi: ts=4 expandtab
