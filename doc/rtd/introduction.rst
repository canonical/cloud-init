Introduction to cloud-init
**************************

Managing and configuring virtual machines (VMs) and servers can be a complex
and time-consuming task. Cloud-init is an open source initialisation tool that
was designed to make it easier to get your systems up and running with a
minimum of effort, and already configured according to your needs.

It’s most often used by developers, system administrators and other IT
professionals to provide instructions to a VM, cloud instance, or machine(s) on
a network. For brevity, we’ll refer only to VMs for the rest of this page, but
assume we’re also including clouds and bare metal in the discussion as well. By
automating routine setup tasks, it ensures repeatability and efficiency in your
system provisioning.

What is the benefit of cloud-init?
==================================

When you deploy a new VM, cloud-init takes an initial configuration that you
supply, and it will automatically apply those settings when the instance is
created. It’s rather like writing a to-do list, and then letting cloud-init
deal with that list for you – like a personal assistant.

The real power of cloud-init comes from the fact that you can re-use your
configuration instructions as often as you want, and always get consistent,
reliable results. If you’re a system administrator and you want to deploy a
whole fleet of machines, you can do so with a fraction of the time and effort
it would take to manually provision them.

What does cloud-init do?
========================

Cloud-init can handle a range of tasks that normally happen when a new VM is
created. It's responsible for activities like setting the hostname, configuring
network interfaces, creating user accounts, and even running scripts. This
streamlines the deployment process; your VMs will all be automatically
configured in the same way, which reduces the chance to introduce human error.

How does cloud-init work?
=========================

There are two primary environments in which cloud-init operates at boot time.
The first is during the “**ephemeral**” boot stage, and the second is during
the “**final**” boot stage.

During ephemeral boot
---------------------

This is the earliest stage where cloud-init runs. The ephemeral boot stage is a
temporary environment that only exists to discover -- and apply -- any
information needed to create the final boot environment.

In the ephemeral stage, most of the tasks cloud-init completes are critical for
initialising the instance. Here, it will:

* **Identify the datasource**:
  The datasource is the source of any configuration data. This can be in the
  form of:
  
  * User-provided data (user data), which allows you to provide custom scripts
    and specific actions that should be taken,
  * Metadata about the instance (metadata) such as the machine ID, hostname and
    network config, or
  * Information about the cloud vendor (vendor data). This might include
    hardware optimisations, or integration with that specific cloud platform.
* **Fetch the datasource**:
  Once the datasource is identified, cloud-init fetches the data. This can
  include e.g. user-defined scripts, network settings, SSH keys, etc. This data
  tells cloud-init what actions to take during boot.
* **Network configuration**:
  Cloud-init sets up network interfaces, assigns IP and MAC addresses, and
  configures DNS. It can also inject SSH keys into the VM’s ``authorized_keys``
  file, which allows secure remote access to the machine.
* **Execute scripts**:
  If any custom scripts were provided in the user data, cloud-init can run
  them. This allows specified software to be installed, security settings to be
  applied, etc.

During final boot
-----------------

In the final boot stage the system has basically been set up, and cloud-init
now runs through the tasks that were not critical for provisioning, but will
configure the running instance according to your needs. It will take care of:

* **Configuration management**:
  Cloud-init can interact with tools like Puppet, Ansible, or Chef to apply
  more complex configuration - and ensure the system is up-to-date.
* **Installing software**:
  Cloud-init can install software at this stage, if it wasn’t done already
  through a custom script. It can also run software updates to make sure the
  system is fully up-to-date and ready to use.
* **User accounts**:
  Cloud-init is able to create and modify user accounts, set default passwords,
  and configure permissions.

After this stage is complete, the instance is ready to use!

What's next?
============

Now that you have an overview of the basics of what cloud-init is, what it does
and how it works, you will probably want to
:ref:`try it out for yourself<tutorial_qemu>`_.

