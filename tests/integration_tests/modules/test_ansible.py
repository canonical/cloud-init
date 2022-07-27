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

       [Service]
       ExecStart=/usr/bin/env python3 -m http.server --directory \
/root/playbooks/.git
       Restart=on-failure

       [Install]
       WantedBy=cloud-final.service

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
INSTALL_METHOD = """
ansible:
  install-method: {}
  package-name: {}
  pull:
    url: "http://0.0.0.0:8000/"
    playbook-name: ubuntu.yml
    full: true
runcmd:
  - "systemctl enable repo_server.service"
"""

SETUP_REPO = f"cd {REPO_D}                                    &&\
git init {REPO_D}                                             &&\
git add {REPO_D}/roles/apt/tasks/main.yml {REPO_D}/ubuntu.yml &&\
git commit -m auto                                            &&\
git update-server-info"


def _test_ansible_pull_from_local_server(my_client):

    assert my_client.execute(SETUP_REPO).ok
    my_client.execute("cloud-init clean --logs")
    my_client.restart()
    log = my_client.read_from_file("/var/log/cloud-init.log")

    # These ensure the repo used for ansible-pull works as expected
    assert my_client.execute("wget http://0.0.0.0:8000").ok
    assert my_client.execute("git clone http://0.0.0.0:8000/").ok
    assert "(dead)" not in my_client.execute(
        "systemctl status repo_server.service"
    )

    # Following assertions verify ansible behavior itself
    assert my_client.execute(["which", "ansible-pull"]).ok
    verify_clean_log(log)
    assert "cc_ansible.py[WARNING]: Error executing" not in log
    assert "SUCCESS: config-ansible ran successfully" in log


@pytest.mark.user_data(USER_DATA + INSTALL_METHOD.format("ansible-core", "pip"))
class TestAnsiblePullPip:
    def test_ansible_pull_pip(self, class_client):
        _test_ansible_pull_from_local_server(class_client)


@pytest.mark.user_data(USER_DATA + INSTALL_METHOD.format("ansible", "distro"))
class TestAnsiblePullDistro:
    def test_ansible_pull_distro(self, class_client):
        _test_ansible_pull_from_local_server(class_client)
