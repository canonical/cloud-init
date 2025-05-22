.. _net-device-info:

Net Device Info
===============

During boot, cloud-init outputs to the terminal a table that
summarizes the information about detected network devices such
as the names of the interfaces, the current states (UP / DOWN),
their IP addresses, their network masks, scopes, and their
hardware (HW) addresses. While this can be useful information
for users, this is actually primarily intended as debug-level
information to analyze scenarios where an instance fails to
boot. The table is not printed in the final stage, therefore, it
may not represent the network’s final state. Rather, it is
indicative of the network topology when it is reaching out to
metadata servers. In many cases the final network configuration
matches the table, but depending on the user supplied
configuration, customizations to the base image, or cloud
environment, it may not be.

Why does the table show interfaces as down?
----------------------------------------------

If the table shows interfaces as down, it means that they were
not activated by the system before the table was printed. This
is not necessarily a problem, and there are a few potential
causes for this.

If the machine successfully boots, you can inspect the network
from the shell and confirm whether or not it matches your
expected setup. This can help determine whether the supplied
configuration took effect. As well, it would likely be worth
inspecting the system journal, cloud-init logs, and following
the :ref:`debugging instructions<how_to_debug>`

Otherwise, it could be that the supplied network configuration
either implicitly or explicitly does not bring up the
interfaces. A good starting place would be to double check the
supplied configuration and run commands.

Limitation using NetworkManager as a renderer on Debian/Ubuntu
--------------------------------------------------------------

An interesting case worth mentioning is that of NetworkManager
on Debian and Ubuntu. This is a known situation where the
expected behaviour is that, although the network will function
as configured, the network device table will not output the
anticipated information. The reason for this comes down to some
implementation details: NetworkManager requires dbus and sysinit
services to be running, however, that is unfortunately not
possible on Debian and Ubuntu at the time of boot when the table
is printed. This is due to the distro-level service orderings in
the service file templates for cloud-init-local and
cloud-init-main. These template files are defined in such a way
as to ensure that cloud-init will be able to interact with the
default packages in each distro's base install image in a
predictable way. The particular constraint on Debian and Ubuntu
is that cloud-init-local must run before sysinit.target, which
is not the case for other distros that may allow or even enforce
that sysinit and dbus run earlier in boot as would be compatible
with the packages they ship. For such distros, the table will
display the expected information.

It is important to reiterate that this issue on Debian and
Ubuntu is merely cosmetic - they will still work as expected and
be able to discover IMDSes in this stage through cloud-init's
local datasource and ephemeral network design paradigm. It just
means cloud-init will not detect the devices as "UP" and the
table's information will not represent the final network
configuration.
