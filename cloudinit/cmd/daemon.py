import socket
import contextlib
import os
import json

from cloudinit.cmd.main import main

@contextlib.contextmanager
def DomainServer(addr):
    try:
        if os.path.exists(addr):
            os.unlink(addr)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(addr)
        sock.listen(10)
        yield sock
    finally:
        sock.close()
        if os.path.exists(addr):
            os.unlink(addr)

addr = "/run/cloud-init/unix.socket"
with DomainServer(addr) as sock:
    expected = set(['local', 'net', 'modules', 'final'])
    completed = set()
    while completed != expected:
        conn, _ = sock.accept()
        data = conn.recv(1024)
        print('Got msg=%s' % data)
        try:
            message = json.loads(data.decode('utf-8'))
        except Exception as e:
            print(e)
            message = None
        if message:
            command = message.get('command')
            if command == 'init-local':
                stage = 'local'
                sysv_args = ['cloud-init', 'init', '--local']
            elif command == 'init-net':
                stage = 'net'
                sysv_args = ['cloud-init', 'init']
            elif command == 'config-modules':
                stage = 'modules'
                sysv_args = ['cloud-init', 'modules', '--mode=config']
            elif command == 'config-final':
                stage = 'final'
                sysv_args = ['cloud-init', 'modules', '--mode=final']

            print('calling main with %s' % sysv_args)
            main(sysv_args=sysv_args)
            print('main call completed')
            completed.add(stage)

        conn.close()
    print('Cloud-init daemon exiting')
