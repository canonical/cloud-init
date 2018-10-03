********************************
Testing and debugging cloud-init
********************************

Overview
========
This topic will discuss general approaches for test and debug of cloud-init on
deployed instances.

.. _boot_time_analysis:

Boot Time Analysis - cloud-init analyze
=======================================
Occasionally instances don't appear as performant as we would like and
cloud-init packages a simple facility to inspect what operations took
cloud-init the longest during boot and setup.

The script **/usr/bin/cloud-init** has an analyze sub-command **analyze**
which parses any cloud-init.log file into formatted and sorted events. It
allows for detailed analysis of the most costly cloud-init operations are to
determine the long-pole in cloud-init configuration and setup. These
subcommands default to reading /var/log/cloud-init.log.

* ``analyze show`` Parse and organize cloud-init.log events by stage and
  include each sub-stage granularity with time delta reports.

.. code-block:: shell-session

    $ cloud-init analyze show -i my-cloud-init.log
    -- Boot Record 01 --
    The total time elapsed since completing an event is printed after the "@"
    character.
    The time the event takes is printed after the "+" character.

    Starting stage: modules-config
    |`->config-emit_upstart ran successfully @05.47600s +00.00100s
    |`->config-snap_config ran successfully @05.47700s +00.00100s
    |`->config-ssh-import-id ran successfully @05.47800s +00.00200s
    |`->config-locale ran successfully @05.48000s +00.00100s
    ...


* ``analyze dump`` Parse cloud-init.log into event records and return a list of
  dictionaries that can be consumed for other reporting needs.

.. code-block:: shell-session

    $ cloud-init analyze dump -i my-cloud-init.log
    [
     {
      "description": "running config modules",
      "event_type": "start",
      "name": "modules-config",
      "origin": "cloudinit",
      "timestamp": 1510807493.0
     },...

* ``analyze blame`` Parse cloud-init.log into event records and sort them based
  on highest time cost for quick assessment of areas of cloud-init that may
  need improvement.

.. code-block:: shell-session

    $ cloud-init analyze blame -i my-cloud-init.log
    -- Boot Record 11 --
         00.01300s (modules-final/config-scripts-per-boot)
         00.00400s (modules-final/config-final-message)
         00.00100s (modules-final/config-rightscale_userdata)
         ...


Analyze quickstart - LXC
---------------------------
To quickly obtain a cloud-init log try using lxc on any ubuntu system:

.. code-block:: shell-session

    $ lxc init ubuntu-daily:xenial x1
    $ lxc start x1
    $ # Take lxc's cloud-init.log and pipe it to the analyzer
    $ lxc file pull x1/var/log/cloud-init.log - | cloud-init analyze dump -i -
    $ lxc file pull x1/var/log/cloud-init.log - | \
      python3 -m cloudinit.analyze dump -i -


Analyze quickstart - KVM
---------------------------
To quickly analyze a KVM a cloud-init log:

1. Download the current cloud image

.. code-block:: shell-session

    $ wget https://cloud-images.ubuntu.com/daily/server/xenial/current/xenial-server-cloudimg-amd64.img

2. Create a snapshot image to preserve the original cloud-image

.. code-block:: shell-session

    $ qemu-img create -b xenial-server-cloudimg-amd64.img -f qcow2 \
    test-cloudinit.qcow2

3. Create a seed image with metadata using `cloud-localds`

.. code-block:: shell-session

    $ cat > user-data <<EOF
      #cloud-config
      password: passw0rd
      chpasswd: { expire: False }
      EOF
    $  cloud-localds my-seed.img user-data

4. Launch your modified VM

.. code-block:: shell-session

    $  kvm -m 512 -net nic -net user -redir tcp:2222::22 \
        -drive file=test-cloudinit.qcow2,if=virtio,format=qcow2 \
        -drive file=my-seed.img,if=virtio,format=raw

5. Analyze the boot (blame, dump, show)

.. code-block:: shell-session

    $ ssh -p 2222 ubuntu@localhost 'cat /var/log/cloud-init.log' | \
       cloud-init analyze blame -i -


Running single cloud config modules
===================================
This subcommand is not called by the init system. It can be called manually to
load the configured datasource and run a single cloud-config module once using
the cached userdata and metadata after the instance has booted. Each
cloud-config module has a module FREQUENCY configured: PER_INSTANCE, PER_BOOT,
PER_ONCE or PER_ALWAYS. When a module is run by cloud-init, it stores a
semaphore file in
``/var/lib/cloud/instance/sem/config_<module_name>.<frequency>`` which marks
when the module last successfully ran. Presence of this semaphore file
prevents a module from running again if it has already been run. To ensure that
a module is run again, the desired frequency can be overridden on the
commandline:

.. code-block:: shell-session

  $ sudo cloud-init single --name cc_ssh --frequency always
  ...
  Generating public/private ed25519 key pair
  ...

Inspect cloud-init.log for output of what operations were performed as a
result.
