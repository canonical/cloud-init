.. _cce-write-files:

Writing out arbitrary files
***************************

For a full list of keys, refer to the `write files module`_ schema.

Write content to file
=====================

This example will write out base64-encoded content to
``/etc/sysconfig/selinux``.

.. code-block:: yaml

    #cloud-config
    write_files:
    - encoding: b64
      content: CiMgVGhpcyBmaWxlIGNvbnRyb2xzIHRoZSBzdGF0ZSBvZiBTRUxpbnV4...
      owner: root:root
      path: /etc/sysconfig/selinux
      permissions: '0644'

Append content to file
======================

This config will append content to an existing file.

.. code-block:: yaml

    #cloud-config
    write_files:
    - content: |
        15 * * * * root ship_logs
      path: /etc/crontab
      append: true

Provide gzipped binary content
==============================

.. code-block:: yaml

    #cloud-config
    write_files:
    - encoding: gzip
      content: !!binary |
          H4sIAIDb/U8C/1NW1E/KzNMvzuBKTc7IV8hIzcnJVyjPL8pJ4QIA6N+MVxsAAAA=
      path: /usr/bin/hello
      permissions: '0755'

Create empty file on the system
===============================

.. code-block:: yaml

    #cloud-config
    write_files:
    - path: /root/CLOUD_INIT_WAS_HERE

Defer writing content
=====================

This example shows how to fefer writing the file until after the Nginx package
is installed and its user is created alongside.

.. code-block:: yaml

    #cloud-config
    write_files:
    - path: /etc/nginx/conf.d/example.com.conf
      content: |
        server {
            server_name example.com;
            listen 80;
            root /var/www;
            location / {
                try_files $uri $uri/ $uri.html =404;
            }
        }
      owner: 'nginx:nginx'
      permissions: '0640'
      defer: true

Example
=======

Encoding can be given as base64 or gzip or (gz+b64).

The content will be decoded accordingly and then written to the path provided.

Note: Content strings here are truncated for example purposes.

.. code-block:: yaml

    #cloud-config
    write_files:
    - encoding: b64
      content: CiMgVGhpcyBmaWxlIGNvbnRyb2xzIHRoZSBzdGF0ZSBvZiBTRUxpbnV4...
      owner: root:root
      path: /etc/sysconfig/selinux
      permissions: '0644'
    - content: |
        # My new /etc/sysconfig/samba file

        SMBDOPTIONS="-D"
      path: /etc/sysconfig/samba
    - content: !!binary |
        f0VMRgIBAQAAAAAAAAAAAAIAPgABAAAAwARAAAAAAABAAAAAAAAAAJAVAAAAAAAAAAAAAEAAOAAI
        AEAAHgAdAAYAAAAFAAAAQAAAAAAAAABAAEAAAAAAAEAAQAAAAAAAwAEAAAAAAADAAQAAAAAAAAgA
        AAAAAAAAAwAAAAQAAAAAAgAAAAAAAAACQAAAAAAAAAJAAAAAAAAcAAAAAAAAABwAAAAAAAAAAQAA
        ....
      path: /bin/arch
      permissions: '0555'
    - encoding: gzip
      content: !!binary |
        H4sIAIDb/U8C/1NW1E/KzNMvzuBKTc7IV8hIzcnJVyjPL8pJ4QIA6N+MVxsAAAA=
      path: /usr/bin/hello
      permissions: '0755'

.. LINKS
.. _write files module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#write-files
