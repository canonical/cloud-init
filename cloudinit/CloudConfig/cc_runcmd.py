import cloudinit
import cloudinit.util as util

def handle(name,cfg,cloud,log,args):
    if not cfg.has_key("runcmd"):
        return
    outfile="%s/runcmd" % cloudinit.user_scripts_dir

    content="#!/bin/sh\n"
    escaped="%s%s%s%s" % ( "'", '\\', "'", "'" )
    try:
        for args in cfg["runcmd"]:
            # if the item is a list, wrap all items in single tick
            # if its not, then just write it directly
            if isinstance(args,list):
                fixed = [ ]
                for f in args:
                    fixed.append("'%s'" % str(f).replace("'",escaped))
                content="%s%s\n" % ( content, ' '.join(fixed) )
            else:
                content="%s%s\n" % ( content, str(args) )

        util.write_file(outfile,content,0700)
    except:
        log.warn("failed to open %s for runcmd" % outfile)
