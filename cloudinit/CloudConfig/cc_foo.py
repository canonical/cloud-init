import cloudinit
import cloudinit.util as util
from cloudinit.CloudConfig import per_instance

frequency = per_instance
def handle(name,cfg,cloud,log,args):
   print "hi"
