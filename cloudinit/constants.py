import os

VAR_LIB_DIR = '/var/lib/cloud'
CUR_INSTANCE_LINK = os.path.join(VAR_LIB_DIR, "instance")
BOOT_FINISHED = os.path.join(CUR_INSTANCE_LINK, "boot-finished")
SEED_DIR = os.path.join(VAR_LIB_DIR, "seed")

CFG_ENV_NAME = "CLOUD_CFG"
CLOUD_CONFIG = '/etc/cloud/cloud.cfg'

CFG_BUILTIN = {
    'datasource_list': ['NoCloud',
                        'ConfigDrive',
                        'OVF',
                        'MAAS',
                        'Ec2',
                        'CloudStack'],
    'def_log_file': '/var/log/cloud-init.log',
    'log_cfgs': [],
    'syslog_fix_perms': 'syslog:adm'
}

PATH_MAP = {
   "handlers": "handlers",
   "scripts": "scripts",
   "sem": "sem",
   "boothooks": "boothooks",
   "userdata_raw": "user-data.txt",
   "userdata": "user-data.txt.i",
   "obj_pkl": "obj.pkl",
   "cloud_config": "cloud-config.txt",
   "data": "data",
}

PER_INSTANCE = "once-per-instance"
PER_ALWAYS = "always"
PER_ONCE = "once"
