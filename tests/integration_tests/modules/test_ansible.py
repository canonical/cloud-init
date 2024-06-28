import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, FOCAL
from tests.integration_tests.util import (
    push_and_enable_systemd_unit,
    verify_clean_log,
)

# This works by setting up a local repository and web server
# daemon on the first boot. Second boot should succeed
# with the running web service and git repo configured.
# This instrumentation allows the test to run self-contained
# without network access or external git repos.

REPO_D = "/root/playbooks"
USER_DATA = """\
#cloud-config
version: v1
package_update: true
package_upgrade: true
packages:
  - git
  - python3-pip
write_files:
  - path: /root/playbooks/ubuntu.yml
    content: |
       ---
       - hosts: 127.0.0.1
         connection: local
         become: true
         vars:
           packages:
             - git
             - python3-pip
         roles:
           - apt
  - path: /root/playbooks/roles/apt/tasks/main.yml
    content: |
       ---
       - name: "install packages"
         apt:
           name: "*"
           update_cache: yes
           cache_valid_time: 3600
       - name: "install packages"
         apt:
           name:
             - "{{ item }}"
           state: latest
         loop: "{{ packages }}"
"""

REPO_SERVER = """\
[Unit]
Description=Serve a local git repo
Wants=repo_waiter.service
After=cloud-init-local.service
Before=cloud-config.service
Before=cloud-final.service

[Install]
WantedBy=cloud-init-local.service

[Service]
WorkingDirectory=/root/playbooks/.git
ExecStart=/usr/bin/env python3 -m http.server --bind 0.0.0.0 8000
"""

REPO_WAITER = """\
[Unit]
Description=Block boot until repo is available
After=repo_server.service
Before=cloud-final.service

[Install]
WantedBy=cloud-init-local.service

# clone into temp directory to test that server is running
# sdnotify would be an alternative way to verify that the server is
# running and continue once it is up, but this is simple and works
[Service]
Type=oneshot
ExecStart=/bin/sh -c "while \
    ! git clone http://0.0.0.0:8000/ $(mktemp -d); do sleep 0.1; done"
"""

INSTALL_METHOD = """
ansible:
  ansible_config: /etc/ansible/ansible.cfg
  install_method: {method}
  package_name: {package}
  galaxy:
    actions:
     - ["ansible-galaxy", "collection", "install", "community.grafana"]
  pull:
    url: "http://0.0.0.0:8000/"
    playbook_name: ubuntu.yml
    full: true
"""

SETUP_REPO = f"cd {REPO_D}                                    &&\
git config --global user.name auto                            &&\
git config --global user.email autom@tic.io                   &&\
git config --global init.defaultBranch main                   &&\
git init {REPO_D}                                             &&\
git add {REPO_D}/roles/apt/tasks/main.yml {REPO_D}/ubuntu.yml &&\
git commit -m auto                                            &&\
(cd {REPO_D}/.git; git update-server-info)"

ANSIBLE_CONTROL = """\
#cloud-config
#
# Demonstrate setting up an ansible controller host on boot.
# This example installs a playbook repository from a remote private repository
# and then runs two of the plays.

package_update: true
package_upgrade: true
packages:
  - git
  - python3-pip

# Set up an ansible user
# ----------------------
# In this case I give the local ansible user passwordless sudo so that ansible
# may write to a local root-only file.
users:
- name: ansible
  gecos: Ansible User
  shell: /bin/bash
  groups: users,admin,wheel,lxd
  sudo: ALL=(ALL) NOPASSWD:ALL

# Initialize lxd using cloud-init.
# --------------------------------
# In this example, a lxd container is
# started using ansible on boot, so having lxd initialized is required.
lxd:
  init:
    storage_backend: dir

# Configure and run ansible on boot
# ---------------------------------
# Install ansible using pip, ensure that community.general collection is
# installed [1].
# Use a deploy key to clone a remote private repository then run two playbooks.
# The first playbook starts a lxd container and creates a new inventory file.
# The second playbook connects to and configures the container using ansible.
# The public version of the playbooks can be inspected here [2]
#
# [1] community.general is likely already installed by pip
# [2] https://github.com/holmanb/ansible-lxd-public
#
ansible:
  install_method: pip
  package_name: ansible
  run_user: ansible
  galaxy:
    actions:
      - ["ansible-galaxy", "collection", "install", "community.general"]

  setup_controller:
    repositories:
      - path: /home/ansible/my-repo/
        source: git@github.com:holmanb/ansible-lxd-private.git
    run_ansible:
      - playbook_dir: /home/ansible/my-repo
        playbook_name: start-lxd.yml
        timeout: 120
        forks: 1
        private_key: /home/ansible/.ssh/id_rsa
      - playbook_dir: /home/ansible/my-repo
        playbook_name: configure-lxd.yml
        become_user: ansible
        timeout: 120
        forks: 1
        private_key: /home/ansible/.ssh/id_rsa
        inventory: new_ansible_hosts

# Write a deploy key to the filesystem for ansible.
# -------------------------------------------------
# This deploy key is tied to a private github repository [1]
# This key exists to demonstrate deploy key usage in ansible
# a duplicate public copy of the repository exists here[2]
#
# [1] https://github.com/holmanb/ansible-lxd-private
# [2] https://github.com/holmanb/ansible-lxd-public
#
write_files:
  - path: /home/ansible/.ssh/known_hosts
    owner: ansible:ansible
    permissions: 0o600
    defer: true
    content: |
      |1|YJEFAk6JjnXpUjUSLFiBQS55W9E=|OLNePOn3eBa1PWhBBmt5kXsbGM4= ssh-ed2551\
9 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl

  - path: /home/ansible/.ssh/id_rsa
    owner: ansible:ansible
    permissions: 0o600
    defer: true
    encoding: base64
    content: |
      LS0tLS1CRUdJTiBPUEVOU1NIIFBSSVZBVEUgS0VZLS0tLS0KYjNCbGJuTnphQzFyWlhrdGRqRUFB
      QUFBQkc1dmJtVUFBQUFFYm05dVpRQUFBQUFBQUFBQkFBQUJsd0FBQUFkemMyZ3RjbgpOaEFBQUFB
      d0VBQVFBQUFZRUEwUWlRa05WQS9VTEpWZzBzT1Q4TEwyMnRGckg5YVR1SWFNT1FiVFdtWjlNUzJh
      VTZ0cDZoClJDYklWSkhmOHdsaGV3MXNvWmphWVVQSFBsUHNISm5UVlhJTnFTTlpEOGF0Rldjd1gy
      ZTNBOElZNEhpN0NMMDE3MVBoMVUKYmJGNGVIT1JaVkY2VVkzLzhmbXQ3NmhVYnpiRVhkUXhQdVdh
      a0IyemxXNTdFclpOejJhYVdnY2pJUGdHV1RNZWVqbEpOcQpXUW9MNlFzSStpeUlzYXNMc1RTajha
      aVgrT1VjanJEMUY4QXNKS3ZWQStKbnVZNUxFeno1TGQ2SGxGc05XVWtoZkJmOWVOClpxRnJCc1Vw
      M2VUY1FtejFGaHFFWDJIQjNQT3VSTzlKemVGcTJaRE8wUlNQN09acjBMYm8vSFVTK3V5VkJNTDNi
      eEF6dEIKQWM5dFJWZjRqcTJuRjNkcUpwVTFFaXZzR0sxaHJZc0VNQklLK0srVzRwc1F5c3ZTL0ZK
      V2lXZmpqWVMwei9IbkV4MkpHbApOUXUrYkMxL1dXSGVXTGFvNGpSckRSZnNIVnVscTE2MElsbnNx
      eGl1MmNHd081V29Fc1NHdThucXB5ZzQzWkhDYjBGd21CCml6UFFEQVNsbmlXanFjS21mblRycHpB
      eTNlVldhd3dsTnBhUWtpZFRBQUFGZ0dLU2o4ZGlrby9IQUFBQUIzTnphQzF5YzIKRUFBQUdCQU5F
      SWtKRFZRUDFDeVZZTkxEay9DeTl0clJheC9XazdpR2pEa0cwMXBtZlRFdG1sT3JhZW9VUW15RlNS
      My9NSgpZWHNOYktHWTJtRkR4ejVUN0J5WjAxVnlEYWtqV1EvR3JSVm5NRjludHdQQ0dPQjR1d2k5
      TmU5VDRkVkcyeGVIaHprV1ZSCmVsR04vL0g1cmUrb1ZHODJ4RjNVTVQ3bG1wQWRzNVZ1ZXhLMlRj
      OW1tbG9ISXlENEJsa3pIbm81U1RhbGtLQytrTENQb3MKaUxHckM3RTBvL0dZbC9qbEhJNnc5UmZB
      TENTcjFRUGlaN21PU3hNOCtTM2VoNVJiRFZsSklYd1gvWGpXYWhhd2JGS2QzawozRUpzOVJZYWhG
      OWh3ZHp6cmtUdlNjM2hhdG1RenRFVWorem1hOUMyNlB4MUV2cnNsUVRDOTI4UU03UVFIUGJVVlgr
      STZ0CnB4ZDNhaWFWTlJJcjdCaXRZYTJMQkRBU0N2aXZsdUtiRU1yTDB2eFNWb2xuNDQyRXRNL3g1
      eE1kaVJwVFVMdm13dGYxbGgKM2xpMnFPSTBhdzBYN0IxYnBhdGV0Q0paN0tzWXJ0bkJzRHVWcUJM
      RWhydko2cWNvT04yUndtOUJjSmdZc3owQXdFcFo0bApvNm5DcG41MDY2Y3dNdDNsVm1zTUpUYVdr
      SkluVXdBQUFBTUJBQUVBQUFHQUV1ejc3SHU5RUVaeXVqTE9kVG5BVzlhZlJ2ClhET1pBNnBTN3lX
      RXVmanc1Q1NsTUx3aXNSODN5d3cwOXQxUVd5dmhScUV5WW12T0JlY3NYZ2FTVXRuWWZmdFd6NDRh
      cHkKL2dRWXZNVkVMR0thSkFDL3E3dmpNcEd5cnhVUGt5TE1oY2tBTFUyS1lnVisvcmovajZwQk1l
      VmxjaG1rM3Bpa1lyZmZVWApKRFk5OTBXVk8xOTREbTBidUxSekp2Zk1LWUYyQmNmRjRUdmFyak9Y
      V0F4U3VSOHd3dzA1MG9KOEhkS2FoVzdDbTVTMHBvCkZSbk5YRkdNbkxBNjJ2TjAwdkpXOFY3ajd2
      dWk5dWtCYmhqUldhSnVZNXJkRy9VWW16QWU0d3ZkSUVucGs5eEluNkpHQ3AKRlJZVFJuN2xUaDUr
      L1FsUTZGWFJQOElyMXZYWkZuaEt6bDBLOFZxaDJzZjRNNzlNc0lVR0FxR3hnOXhkaGpJYTVkbWdw
      OApOMThJRURvTkVWS1ViS3VLZS9aNXlmOFo5dG1leGZIMVl0dGptWE1Pb2pCdlVISWpSUzVoZEk5
      TnhuUEdSTFkya2pBemNtCmdWOVJ2M3Z0ZEYvK3phbGszZkFWTGVLOGhYSytkaS83WFR2WXBmSjJF
      WkJXaU5yVGVhZ2ZOTkdpWXlkc1F5M3pqWkFBQUEKd0JOUmFrN1VycW5JSE1abjdwa0NUZ2NlYjFN
      ZkJ5YUZ0bE56ZCtPYmFoNTRIWUlRajVXZFpUQkFJVFJlTVpOdDlTNU5BUgpNOHNRQjhVb1pQYVZT
      QzNwcElMSU9mTGhzNktZajZSckdkaVl3eUloTVBKNWtSV0Y4eEdDTFVYNUNqd0gyRU9xN1hoSVd0
      Ck13RUZ0ZC9nRjJEdTdIVU5GUHNaR256SjNlN3BES0RuRTd3MmtoWjhDSXBURmdENzY5dUJZR0F0
      azQ1UVlURG81SnJvVk0KWlBEcTA4R2IvUmhJZ0pMbUlwTXd5cmVWcExMTGU4U3dvTUpKK3JpaG1u
      Slp4TzhnQUFBTUVBMGxoaUtlemVUc2hodDR4dQpyV2MwTnh4RDg0YTI5Z1NHZlRwaERQT3JsS1NF
      WWJrU1hoanFDc0FaSGQ4UzhrTXIzaUY2cG9PazNJV1N2Rko2bWJkM2llCnFkUlRnWEg5VGh3azRL
      Z3BqVWhOc1F1WVJIQmJJNTlNbytCeFNJMUIxcXptSlNHZG1DQkw1NHd3elptRktEUVBRS1B4aUwK
      bjBNbGM3R29vaURNalQxdGJ1Vy9PMUVMNUVxVFJxd2dXUFRLaEJBNnI0UG5HRjE1MGhaUklNb29a
      a0Qyelg2YjFzR29qawpRcHZLa0V5a1R3bktDekY1VFhPOCt3SjNxYmNFbzlBQUFBd1FEK1owcjY4
      YzJZTU5wc215ajNaS3RaTlBTdkpOY0xteUQvCmxXb05KcTNkakpONHMySmJLOGw1QVJVZFczeFNG
      RURJOXl4L3dwZnNYb2FxV255Z1AzUG9GdzJDTTRpMEVpSml5dnJMRlUKcjNKTGZEVUZSeTNFSjI0
      UnNxYmlnbUVzZ1FPelRsM3hmemVGUGZ4Rm9PaG9rU3ZURzg4UFFqaTFBWUh6NWtBN3A2WmZhegpP
      azExckpZSWU3K2U5QjBsaGt1MEFGd0d5cWxXUW1TL01oSXBuakhJazV0UDRoZUhHU216S1FXSkRi
      VHNrTldkNmFxMUc3CjZIV2ZEcFg0SGdvTThBQUFBTGFHOXNiV0Z1WWtCaGNtTT0KLS0tLS1FTkQg
      T1BFTlNTSCBQUklWQVRFIEtFWS0tLS0tCg==


# Work around this bug [1] by dropping the second interface after it is no
# longer required
# [1] https://github.com/canonical/pycloudlib/issues/220
runcmd:
  - [ip, link, delete, lxdbr0]
"""


def _test_ansible_pull_from_local_server(my_client):
    setup = my_client.execute(SETUP_REPO)
    assert not setup.stderr
    assert not setup.return_code
    my_client.execute("cloud-init clean --logs")
    my_client.restart()
    log = my_client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    output_log = my_client.read_from_file("/var/log/cloud-init-output.log")
    assert "ok=3" in output_log
    assert "SUCCESS: config-ansible ran successfully" in log

    # binary location is dependent on install-type, check the filepath
    # to ensure that the installed collection directory exists
    output = my_client.execute(
        "ls /root/.ansible/collections/ansible_collections/community/grafana"
    )
    assert not output.stderr.strip() and output.ok


# temporarily disable this test on jenkins until firewall rules are in place
@pytest.mark.adhoc
@pytest.mark.user_data(
    USER_DATA + INSTALL_METHOD.format(package="ansible-core", method="pip")
)
def test_ansible_pull_pip(client: IntegrationInstance):
    push_and_enable_systemd_unit(client, "repo_server.service", REPO_SERVER)
    push_and_enable_systemd_unit(client, "repo_waiter.service", REPO_WAITER)
    _test_ansible_pull_from_local_server(client)


# temporarily disable this test on jenkins until firewall rules are in place
@pytest.mark.adhoc
# Ansible packaged in bionic is 2.5.1. This test relies on ansible collections,
# which requires Ansible 2.9+, so no bionic. The functionality is covered
# in `test_ansible_pull_pip` using pip rather than the bionic package.
@pytest.mark.skipif(
    CURRENT_RELEASE < FOCAL, reason="Test requires Ansible 2.9+"
)
@pytest.mark.user_data(
    USER_DATA + INSTALL_METHOD.format(package="ansible", method="distro")
)
def test_ansible_pull_distro(client):
    push_and_enable_systemd_unit(client, "repo_server.service", REPO_SERVER)
    push_and_enable_systemd_unit(client, "repo_waiter.service", REPO_WAITER)
    _test_ansible_pull_from_local_server(client)


@pytest.mark.user_data(ANSIBLE_CONTROL)
@pytest.mark.skipif(
    PLATFORM != "lxd_vm",
    reason="Test requires starting LXD containers",
)
@pytest.mark.skipif(
    CURRENT_RELEASE < FOCAL,
    reason="Pip install is not supported for Ansible on release",
)
@pytest.mark.skip(reason="Need proxy support first. GH: #4527")
def test_ansible_controller(client):
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    content_ansible = client.execute(
        "lxc exec lxd-container-00 -- cat /home/ansible/ansible.txt"
    )
    content_root = client.execute(
        "lxc exec lxd-container-00 -- cat /root/root.txt"
    )
    assert content_ansible == "hello as ansible"
    assert content_root == "hello as root"
