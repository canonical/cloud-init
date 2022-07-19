import pytest

from tests.integration_tests.util import verify_clean_log

# This works by setting up a local repository and web server
# daemon on the first boot. Second boot should run successfully
# with the running web service and git repo configured

REPO_D = "/root/playbooks"
USER_DATA = """\
#cloud-config
version: v1
packages_update: true
packages_upgrade: true
packages:
  - ansible
  - git
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


ansible:
  install: false
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


@pytest.mark.user_data(USER_DATA)
class TestAnsiblePull:
    def test_ansible_pull_from_local_server(self, class_client):

        assert class_client.execute(SETUP_REPO).ok
        class_client.execute("cloud-init clean --logs")
        class_client.restart()
        log = class_client.read_from_file("/var/log/cloud-init.log")

        # These ensure the repo used for ansible-pull works as expected
        assert class_client.execute("wget http://0.0.0.0:8000").ok
        assert class_client.execute("git clone http://0.0.0.0:8000/").ok
        assert "(dead)" not in class_client.execute(
            "systemctl status repo_server.service"
        )

        # Following assertions verify ansible behavior itself
        assert class_client.execute(["which", "ansible-pull"]).ok
        verify_clean_log(log)
        assert "cc_ansible.py[WARNING]: Error executing" not in log
        assert "SUCCESS: config-ansible ran successfully" in log
