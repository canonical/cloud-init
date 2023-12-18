#!/usr/bin/python3

import sys
import os

# DECLARE AFTER THIS FOR TESTING CLOUDINIT

from cloudinit.config import cc_chef

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers

from cloudinit.sources import DataSourceNoCloud

from cloudinit import log as logging
cfg = {
    'datasource': {'NoCloud': {'fs_label': None}}
}

LOG = logging.getLogger(__name__)

logging.setupLogging(cfg)

def _get_cloud(distro):
    paths = helpers.Paths({})
    cls = distros.fetch(distro)
    d = cls(distro, {}, paths)
    ds = DataSourceNoCloud.DataSourceNoCloud({}, d, paths)
    cc = cloud.Cloud(ds, paths, {}, d, None)
    return cc

cfg = {
    'chef': {
        'install_type': 'gems',
        'force_install': True,
        'server_url': 'https://sysmgt-hmc1.austin.ibm.com',
        'node_name': 'isotopes02',
        'environment': 'production',
        'validation_name': "yourorg-validator",
        'validation_cert': '-----BEGIN RSA PRIVATE KEY-----\nBLAHBLAH\n-----END RSA PRIVATE KEY-----\n',
        'validation_key': '-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA3Y8rAIkjch0DXttMGBGNNb0iehNY/RDTK9j5mESfc3tW4JcKkC5iXxViL3WThxZkntbmy1yXeLfJxrSh0FlaPCLzpwMzcdS8/Y031hT7Durz8LPeq3IjiPJMErdmvLgewJsbv18qqQl1yPAAuGQ5zYf40qBR0WW2azGBnkASa9ai38WzcMFPPeJ4vQGdoc9rmD/Q7ah5DkiuuMM5z//FlhzGdZGWrxlvaAl/Xki2ZmlDsMcgc6q0hbDd6HahWKX5SF50iMBmL1j4SHRG0Ntjz7OXkDFAl5l5YQYJOJaqzXjJKtIMV79XFK72sYYu/gtBdiP34NSHHGTiPrQDDHbvWwIDAQABAoIBABVdqRf0IabvhVOwcjYf+y4jfx+mnf5JkRO5aNh2RaotSsN9zVb6IiJpPX62J/PvBOUMdFVIKJNLpfmzkac19q218Sk59cwUZ+VLqQbMHynhHoUn02FVMHgUZaGobg/k8ZJBYvuhgcurTeCCxI8Dm09mvWgSbdFzrZPIwmcwZpZffoXmXxPSPBNXVa3u9eSWDtpO/P/Mrq0VAFrZZVRg3ovdKOX2NjnyFdrYAqNUuESfRKnNVuuHaX+hxvW4oAFriduK8xM/pDSNCiIdfnD0AnG/OEFsZB6HQpyFpFR/TdC2GP37IBUVvnCbJTGvqSHDDLXR8xTj9HJXcp07MN8FyoECgYEA8GY9D1D8fT8YFktE/omNag2Mgb3aHkbjqBk8CNO7bPiQb5vnIwja6lZ+IuWVWjmZDVL2CSoKpDHdIIYNL8xzr+bLIszyRAL4FGGyIUKfLvyRHmHeRT4Eew+w4f8rYeTti6B7LdIl4hIq2dRy1x+MiYCxz4TV0JvtGAj+VhqvFJ8CgYEA6+/wIr00TEKz+9S1Vl0e3oeMIJKSyoFAMBuRjcEJ5gioqa5HcljIks2UiWESKT6np2qymdhGbBKPbBFqgf3Lbgk9LYNPc6oPSGQuW2kxsvioOaQXIcsv1+0w0zViHiIRARoNEGrKkerL0SoAwhmge1N5kwTdSBHPFTM0x8BBT8UCgYEA70UDLxRvSgWbZs0h7apgyxaTK6sXxpzOCEidfTeoS4yWzc9BXZh5s1XFE9yoK3Y6hI12/qYOk2Bh8/YYd+OpnYE72/ZahyDhY//c+MfDglO16KSGQyq38PgsGLQNrNDbMebX00JfnERyy/5tEvp+uXkTATX4Tjpz4EFLS84hRocCgYEA38EwozF+zKgh2z3yMBKmOPKh8S4wqn6Dqlwq4R3mzlL96dYPiiErLxZqvRLjT1xNUZf+A6s5tjqv7BRkRx2zdQqsC2LR0ebBEa14zVZpPMtXdzroeTMij4wx1sx03hD+wWW8aApvTI05eId2Kp51NSCIVuaxGS1SkE98ycfJ6OUCgYA4zgurTeB6VZF7VO408zX3cCmUlbYeNgEA1DsHcWAjZUdV2iYj/xxoO04neMq+NtvR0cHgru2xSdy2WmZusOCAsaNkJchMevklhVU1rGMIfghJgdSu7RMXSMUBY3wGpTmiyRcsCu4SUUV8UDCi2yqPAeXwr8Z8qN+3K33sC0LjUQ==\n-----END RSA PRIVATE KEY-----\n',
        'run_list': ['recipe[apache2]', 'role[db]'],
        'initial_attributes': {
            'apache': {
                'prefork': {
                    'maxclients': 100,
                 },
            },
            'keepalive': 'off'
        },
        'omnibus_url': 'https://www.opscode.com/chef/install.sh',
        'output': { 'all': '| tee -a /var/log/cloud-init-output.log'},
    },
}

cc = _get_cloud('aix')

cc_chef.handle('cc_chef', cfg, cc, LOG, [])
