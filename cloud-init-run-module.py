#!/usr/bin/python

import sys
import ec2init

def Usage(out = sys.stdout):
    out.write("Usage: cloud-init-run-module freq sem-name mod-name [args]")
    
def main():
    # expect to be called with
    #   <freq> <semaphore-name> <module-name> args
    if len(sys.argv) < 4:
        Usage(sys.stderr)
        sys.exit(1)

    (freq,semname,modname)=sys.argv[1:4]
    run_args=sys.argv[4:]

    if ec2init.sem_has_run(semname,freq):
        sys.stderr.write("%s already ran %s\n" % (semname,freq))
        sys.exit(0)

    try:
        mod = __import__('ec2init.' + modname)
        inst = getattr(mod,modname)
    except:
        sys.stderr.write("Failed to load module ec2init.%s\n" % modname)
        sys.exit(1)

    import os

    cfg_path = None
    cfg_env_name = "CLOUD_CFG"
    if os.environ.has_key(cfg_env_name):
        cfg_path = os.environ[cfg_env_name]

    try:
        if not ec2init.sem_acquire(semname,freq):
            sys.stderr.write("Failed to acquire lock on %s\n" % semname)
            sys.exit(1)

        inst.run(run_args,cfg_path)
    except:
        ec2init.sem_clear(semname,freq)
        raise

    sys.exit(0)

if __name__ == '__main__':
    main()
