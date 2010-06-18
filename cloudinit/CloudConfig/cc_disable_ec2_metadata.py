import cloudinit.util as util
from cloudinit.CloudConfig import per_always

frequency = per_always

def handle(name,cfg,cloud,log,args):
    if util.get_cfg_option_bool(cfg, "disable_ec2_metadata", False):
        fwall="route add -host 169.254.169.254 reject"
        subprocess.call(fwall.split(' '))
