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

* ``analyze boot`` Make subprocess calls to the kernel in order to get relevant
  pre-cloud-init timestamps, such as the kernel start, kernel finish boot, and cloud-init start.

.. code-block:: shell-session

    $ cloud-init analyze boot
    -- Most Recent Boot Record --
        Kernel Started at: 2019-06-13 15:59:55.809385
        Kernel ended boot at: 2019-06-13 16:00:00.944740
        Kernel time to boot (seconds): 5.135355
        Cloud-init start: 2019-06-13 16:00:05.738396
        Time between Kernel boot and Cloud-init start (seconds): 4.793656


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

.. _proposed_sru_testing:

Stable Release Updates (SRU) testing for cloud-init
===================================================
Once an Ubuntu release is stable (i.e. after it is released), updates for it
must follow a special procedure called a "stable release update" (or `SRU`_).

The cloud-init project has a specific process it follows when validating
a cloud-init SRU, documented in the `CloudinitUpdates`_ wiki page.

Generally an SRU test of cloud-init performs the following:

 * Install a pre-release version of cloud-init from the
   **-proposed** APT pocket (e.g. **bionic-proposed**)
 * Upgrade cloud-init and attempt a clean run of cloud-init to assert the new
   version of cloud-init works properly the specific platform and Ubuntu series
 * Check for tracebacks or errors in behavior


Manual SRU verification procedure
---------------------------------
Below are steps to manually test a pre-release version of cloud-init
from **-proposed**

.. note::
    For each Ubuntu SRU, the Ubuntu Server team manually validates the new version of cloud-init
    on these platforms: **Amazon EC2, Azure, GCE, OpenStack, Oracle,
    Softlayer (IBM), LXD, KVM**

1. Launch a VM on your favorite platform, providing this cloud-config
   user-data and replacing `<YOUR_LAUNCHPAD_USERNAME>` with your username:

.. code-block:: yaml

    ## template: jinja
    #cloud-config
    ssh_import_id: [<YOUR_LAUNCHPAD_USERNAME>]
    hostname: SRU-worked-{{v1.cloud_name}}

2. Wait for current cloud-init to complete, replace `<YOUR_VM_IP>` with the IP
   address of the VM that you launched in step 1:

.. code-block:: bash

    CI_VM_IP=<YOUR_VM_IP>
    # Make note of the datasource cloud-init detected in --long output.
    # In step 5, you will use this to confirm the same datasource is detected after upgrade.
    ssh ubuntu@$CI_VM_IP -- cloud-init status --wait --long

3. Set up the **-proposed** pocket on your VM and upgrade to the **-proposed**
   cloud-init:

.. code-block:: bash

    # Create a script that will add the -proposed pocket to APT's sources
    # and install cloud-init from that pocket
    cat > setup_proposed.sh <<EOF
    #/bin/bash
    mirror=http://archive.ubuntu.com/ubuntu
    echo deb \$mirror \$(lsb_release -sc)-proposed main | tee \
        /etc/apt/sources.list.d/proposed.list
    apt-get update -q
    apt-get install -qy cloud-init
    EOF

    scp setup_proposed.sh ubuntu@$CI_VM_IP:.
    ssh ubuntu@$CI_VM_IP -- sudo bash setup_proposed.sh

4. Change hostname, clean cloud-init's state, and reboot to run cloud-init
   from scratch:

.. code-block:: bash

    ssh ubuntu@$CI_VM_IP -- sudo hostname something-else
    ssh ubuntu@$CI_VM_IP -- sudo cloud-init clean --logs --reboot

5. Validate **-proposed** cloud-init came up without error

.. code-block:: bash

    # Block until cloud-init completes and verify from --long the datasource
    # from step 1. Errors would show up in --long

    ssh ubuntu@$CI_VM_IP -- cloud-init status --wait --long
    # Make sure hostname was set properly to SRU-worked-<cloud name>
    ssh ubuntu@$CI_VM_IP -- hostname
    # Check for any errors or warnings in cloud-init logs.
    # (This should produce no output if successful.)
    ssh ubuntu@$CI_VM_IP -- grep Trace "/var/log/cloud-init*"

6. If you encounter an error during SRU testing:

   * Create a `new cloud-init bug`_ reporting the version of cloud-init
     affected
   * Ping upstream cloud-init on Freenode's `#cloud-init IRC channel`_

.. _SRU: https://wiki.ubuntu.com/StableReleaseUpdates
.. _CloudinitUpdates: https://wiki.ubuntu.com/CloudinitUpdates
.. _new cloud-init bug: https://bugs.launchpad.net/cloud-init/+filebug
.. _#cloud-init IRC channel: https://webchat.freenode.net/?channel=#cloud-init
