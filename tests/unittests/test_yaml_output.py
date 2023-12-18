#!/usr/bin/python3

import yaml
document = """
    chpasswd:
        list: |
            root1:nimfvt1
            user2:password1
        expire: False

    users:
        - default
        - name: foobar
          gecos: Foo B. Bar
          groups: staff
          sudo: ALL=(ALL) NOPASSWD:ALL

    manage_resolv_conf: True
    resolv_conf:
        nameservers:
            - 9.3.1.200
            - 9.0.128.50
            - 9.0.130.50
        searchdomains:
            - austin.ibm.com
            - aus.stglabs.ibm.com
        domain: austin.ibm.com

    chef:
        install_type: "packages"
        force_install: False
        server_url: "https://tranwin.austin.ibm.com"
        node_name: "isotopes02"
        environment: "production"
        exec: True
        validation_name: "yourorg-validator"
        validation_key: "/etc/chef/validation.pem"
        validation_cert: |
            -----BEGIN RSA PRIVATE KEY-----
            YOUR-ORGS-VALIDATION-KEY-HERE
            -----END RSA PRIVATE KEY-----
        run_list:
            - "recipe[apache2]"
            - "role[db]"
        initial_attributes:
            apache:
                prefork:
                    maxclients: 100
                keepalive: "off"

        omnibus_url: "https://www.opscode.com/chef/install.sh"
        output: { 'all': '| tee -a /var/log/cloud-init-output.log'}

    write_files:
        - path: /tmp/test.txt
          content: |
              Here is a line.
              Another line is here.

    users:
        - name: demo
          groups: sudo
          shell: /bin/bash
          sudo: ['ALL=(ALL) NOPASSWD:ALL']
          ssh-authorized-keys:
              - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDf0q4PyG0doiBQYV7OlOxbRjle026hJPBWD+eKHWuVXIpAiQlSElEBqQn0pOqNJZ3IBCvSLnrdZTUph4czNC4885AArS9NkyM7lK27Oo8RV888jWc8hsx4CD2uNfkuHL+NI5xPB/QT3Um2Zi7GRkIwIgNPN5uqUtXvjgA+i1CS0Ku4ld8vndXvr504jV9BMQoZrXEST3YlriOb8Wf7hYqphVMpF3b+8df96Pxsj0+iZqayS9wFcL8ITPApHi0yVwS8TjxEtI3FDpCbf7Y/DmTGOv49+AWBkFhS2ZwwGTX65L61PDlTSAzL+rPFmHaQBHnsli8U9N6E4XHDEOjbSMRX user@example.com
              - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDcthLR0qW6y1eWtlmgUE/DveL4XCaqK6PQlWzi445v6vgh7emU4R5DmAsz+plWooJL40dDLCwBt9kEcO/vYzKY9DdHnX8dveMTJNU/OJAaoB1fV6ePvTOdQ6F3SlF2uq77xYTOqBiWjqF+KMDeB+dQ+eGyhuI/z/aROFP6pdkRyEikO9YkVMPyomHKFob+ZKPI4t7TwUi7x1rZB1GsKgRoFkkYu7gvGak3jEWazsZEeRxCgHgAV7TDm05VAWCrnX/+RzsQ/1DecwSzsP06DGFWZYjxzthhGTvH/W5+KFyMvyA+tZV4i1XM+CIv/Ma/xahwqzQkIaKUwsldPPu00jRN user@desktop
          runcmd:
              - touch /tmp/test.txt

    groups:
        - group1
        - group2: [demo]

    runcmd:
    - echo 'Instance has been configured by cloud-init.' | wall

    instance-id:
        default: iid-dsconfigdrive
"""

print(yaml.load(document))

