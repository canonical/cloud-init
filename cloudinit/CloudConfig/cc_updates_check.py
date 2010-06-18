import cloudinit.util as util
import cloudinit
import os
import time

cronpre = "/etc/cron.d/cloudinit"

def handle(name,cfg,cloud,log,args):
    if not util.get_cfg_option_bool(cfg, 'updates-check', True):
        return
    build_info = "/etc/cloud/build.info"
    if not os.path.isfile(build_info):
        log.warn("no %s file" % build_info)

    avail="%s/%s" % ( cloudinit.datadir, "available.build" )
    cmd=( "uec-query-builds", "--system-suite", "--config", "%s" % build_info,
          "--output", "%s" % avail, "is-update-available" )
    try:
        util.subp(cmd)
    except:
        log.warn("failed to execute uec-query-build for updates check")

    # add a cron entry for this hour and this minute every day
    try:
        cron=open("%s-%s" % (cronpre, "updates") ,"w")
        cron.write("%s root %s\n" % \
            (time.strftime("%M %H * * *"),' '.join(cmd)))
        cron.close()
    except:
        log.warn("failed to enable cron update system check")
        raise

