.. _introduction:

Introduction to cloud-init
**************************

Managing and configuring cloud instances and servers can be a complex
and time-consuming task. Cloud-init is an open source initialisation tool that
was designed to make it easier to get your systems up and running with a
minimum of effort, already configured according to your needs.

It’s most often used by developers, system administrators and other IT
professionals to automate configuration of VMs, cloud instances, or machines on
a network. For brevity, we’ll refer only to instances for the rest of this
page, but assume we’re also including bare metal and VMs in the discussion as
well. By automating routine setup tasks, cloud-init ensures repeatability and
efficiency in your system provisioning.

What is the benefit of cloud-init?
==================================

When you deploy a new cloud instance, cloud-init takes an initial configuration
that you supply, and it automatically applies those settings when the instance
is created. It’s rather like writing a to-do list, and then letting cloud-init
deal with that list for you.

The real power of cloud-init comes from the fact that you can re-use your
configuration instructions as often as you want, and always get consistent,
reliable results. If you’re a system administrator and you want to deploy a
whole fleet of machines, you can do so with a fraction of the time and effort
it would take to manually provision them.

What does cloud-init do?
========================

Cloud-init can handle a range of tasks that normally happen when a new instance
is created. It's responsible for activities like setting the hostname,
configuring network interfaces, creating user accounts, and even running
scripts. This streamlines the deployment process; your cloud instances will all
be automatically configured in the same way, which reduces the chance to
introduce human error.

How does cloud-init work?
=========================

The operation of cloud-init broadly takes place in two separate phases during
the boot process. The first phase is during the early (local) boot stage,
before networking has been enabled. The second is during the late boot stages,
after cloud-init has applied the networking configuration.

During early boot
-----------------

In this pre-networking stage, cloud-init discovers the datasource, obtains
all the configuration data from it, and configures networking. In this phase,
it will:

* **Identify the datasource**:
  The hardware is checked for built-in values that will identify the datasource
  your instance is running on. The datasource is the source of all
  configuration data.
* **Fetch the configuration**:
  Once the datasource is identified, cloud-init fetches the configuration data
  from it. This data tells cloud-init what actions to take. This can be in the
  form of:

  * **Metadata** about the instance, such as the machine ID, hostname and
    network config, or
  * **Vendor data** and/or **user data**. These take the same form, although
    Vendor data is provided by the cloud vendor, and user data is provided by
    the user. These data are usually applied in the post-networking phase, and
    might include:

    * Hardware optimisations
    * Integration with the specific cloud platform
    * SSH keys
    * Custom scripts

* **Write network configuration**:
  Cloud-init writes the network configuration and configures DNS, ready to be
  applied by the networking services when they come up.

During late boot
----------------

In the boot stages that come after the network has been configured, cloud-init
runs through the tasks that were not critical for provisioning. This is where
it configures the running instance according to your needs, as specified in the
vendor data and/or user data. It will take care of:

* **Configuration management**:
  Cloud-init can interact with tools like Puppet, Ansible, or Chef to apply
  more complex configuration - and ensure the system is up-to-date.
* **Installing software**:
  Cloud-init can install software at this stage, and run software updates to
  make sure the system is fully up-to-date and ready to use.
* **User accounts**:
  Cloud-init is able to create and modify user accounts, set default passwords,
  and configure permissions.
* **Execute user scripts**:
  If any custom scripts were provided in the user data, cloud-init can run
  them. This allows additional specified software to be installed, security
  settings to be applied, etc. It can also inject SSH keys into the instance’s
  ``authorized_keys`` file, which allows secure remote access to the machine.

After this stage is complete, your instance is fully configured!

What's next?
============

Now that you have an overview of the basics of what cloud-init is, what it does
and how it works, you will probably want to
:ref:`try it out for yourself<tutorial_qemu>`.

You can also read in more detail about what cloud-init does
:ref:`during the different boot stages<boot_stages>`, and the
:ref:`types of configuration<configuration>` you can pass to cloud-init and
how they're used.

