#!/usr/bin/python

import sys
import cloudinit

def Usage(out = sys.stdout):
    out.write("Usage: cloud-init-run-module freq sem-name mod-name [args]\n")
    
def main():
    # expect to be called with
    #   <freq> <semaphore-name> <module-name> args
    if len(sys.argv) < 4:
        Usage(sys.stderr)
        sys.exit(1)

    (freq,semname,modname)=sys.argv[1:4]
    run_args=sys.argv[4:]

    cloud = cloudinit.EC2Init()
    try:
        cloud.get_data_source()
    except Exception as e:
        print e
        sys.stderr.write("Failed to get instance data")
        sys.exit(1)

    if cloud.sem_has_run(semname,freq):
        sys.stderr.write("%s already ran %s\n" % (semname,freq))
        sys.exit(0)

    try:
        mod = __import__('cloudinit.' + modname)
        inst = getattr(mod,modname)
    except:
        sys.stderr.write("Failed to load module cloudinit.%s\n" % modname)
        sys.exit(1)

    import os

    cfg_path = None
    cfg_env_name = cloudinit.cfg_env_name
    if os.environ.has_key(cfg_env_name):
        cfg_path = os.environ[cfg_env_name]

    cloud.sem_and_run(semname, freq, inst.run, [run_args,cfg_path], False)

    sys.exit(0)

if __name__ == '__main__':
    main()
