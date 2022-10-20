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
    def test_ansible_pull_pip(self, class_client):
        _test_ansible_pull_from_local_server(class_client)


# temporarily disable this test on jenkins until firewall rules are in place
@pytest.mark.adhoc
@pytest.mark.user_data(
    USER_DATA + INSTALL_METHOD.format(package="ansible", method="distro")
)
class TestAnsiblePullDistro:
    def test_ansible_pull_distro(self, class_client):
        _test_ansible_pull_from_local_server(class_client)
