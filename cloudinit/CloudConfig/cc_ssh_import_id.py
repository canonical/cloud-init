import cloudinit.util as util
import subprocess
import traceback

def handle(name,cfg,cloud,log,args):
    if len(args) != 0:
        user = args[0]
        ids = [ ]
        if len(args) > 1:
            ids = args[1:]
    else:
        user = util.get_cfg_option_str(cfg,"user","ubuntu")
        ids = util.get_cfg_option_list_or_str(cfg,"ssh_import_id",[])

    log.warn("here, args = %s.  user = %s ids = %s" % ( args, user, ids ))
    if len(ids) == 0: return

    cmd = [ "sudo", "-Hu", user, "ssh-import-lp-id" ] + ids

    log.debug("importing ssh ids. cmd = %s" % cmd)

    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        log.debug(traceback.format_exc(e))
        raise Exception("Cmd returned %s: %s" % ( e.returncode, cmd))
    except OSError as e:
        log.debug(traceback.format_exc(e))
        raise Exception("Cmd failed to execute: %s" % ( cmd ))
