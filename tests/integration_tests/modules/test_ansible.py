import pytest

from tests.integration_tests.util import verify_clean_log

# This works by setting up a local repository and web server
# daemon on the first boot. Second boot should succeed
# with the running web service and git repo configured.
# This instrumentation allows the test to run self-contained
# without network access or external git repos.

REPO_D = "/root/playbooks"
USER_DATA = """\
#cloud-config
version: v1
packages_update: true
packages_upgrade: true
packages:
  - git
  - python3-pip
write_files:
  - path: /etc/systemd/system/repo_server.service
    content: |
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

  - path: /etc/systemd/system/repo_waiter.service
    content: |
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

runcmd:
  - [systemctl, enable, repo_server.service]
  - [systemctl, enable, repo_waiter.service]
"""

INSTALL_METHOD = """
ansible:
  ansible_config: /etc/ansible/ansible.cfg
  install-method: {method}
  package-name: {package}
  galaxy:
    actions:
     - ["ansible-galaxy", "collection", "install", "community.grafana"]
  pull:
    url: "http://0.0.0.0:8000/"
    playbook-name: ubuntu.yml
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

packages_update: true
packages_upgrade: true
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
  install-method: pip
  package-name: ansible
  run-user: ansible
  galaxy:
    actions:
      - ["ansible-galaxy", "collection", "install", "community.general"]

  setup_controller:
    repositories:
      - path: /home/ansible/my-repo/
        source: git@github.com:holmanb/ansible-lxd-private.git
    run_ansible:
      - playbook-dir: /home/ansible/my-repo
        playbook-name: start-lxd.yml
        timeout: 120
        forks: 1
        private-key: /home/ansible/.ssh/id_rsa
      - playbook-dir: /home/ansible/my-repo
        playbook-name: configure-lxd.yml
        become-user: ansible
        timeout: 120
        forks: 1
        private-key: /home/ansible/.ssh/id_rsa
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
    content: |
      -----BEGIN OPENSSH PRIVATE KEY-----
      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
      6HWfDpX4HgoM8AAAALaG9sbWFuYkBhcmM=
      -----END OPENSSH PRIVATE KEY-----

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
class TestAnsiblePullPip:
    def test_ansible_pull_pip(self, client):
        _test_ansible_pull_from_local_server(client)


# temporarily disable this test on jenkins until firewall rules are in place
@pytest.mark.adhoc
@pytest.mark.user_data(
    USER_DATA + INSTALL_METHOD.format(package="ansible", method="distro")
)
class TestAnsiblePullDistro:
    def test_ansible_pull_distro(self, class_client):
        _test_ansible_pull_from_local_server(class_client)


@pytest.mark.user_data(ANSIBLE_CONTROL)
@pytest.mark.lxd_vm
class TestAnsibleController:
    def test_ansible_controller(self, client):
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
