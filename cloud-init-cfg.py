#!/usr/bin/python

import sys
import cloudinit

def Usage(out = sys.stdout):
    out.write("Usage: %s name\n" % sys.argv[0])
    
def main():
    # expect to be called with
    #   name freq [ args ]
    if len(sys.argv) < 2:
        Usage(sys.stderr)
        sys.exit(1)

    name=sys.argv[1]
    run_args=sys.argv[2:]

    import cloudinit.CloudConfig
    import os

    cfg_path = cloudinit.cloud_config
    cfg_env_name = cloudinit.cfg_env_name
    if os.environ.has_key(cfg_env_name):
        cfg_path = os.environ[cfg_env_name]

    cc = cloudinit.CloudConfig.CloudConfig(cfg_path)

    try:
        cc.handle(name,run_args)
    except:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.write("config handling of %s failed\n" % name)
        sys.exit(1)

    sys.exit(0)

if __name__ == '__main__':
    main()
