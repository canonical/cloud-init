API design for the new distros namespace
========================================

API convention
--------------

Before dwelving into the details of the proposed API, some conventions
should be established, so that the API could be pythonic, easy to
comprehend and extend. We have the following examples of how an object
should look, depending on its state and behaviour:

 - Use ``.attribute`` if the attribute is not changeable
   throughout the life of the object.
   For instance, the name of a device.

 - Use ``.method()`` for obtaining a variant attribute, which can be
   different throughout the execution of the object and not modifiable
   through our object. This is the case for ``device.size()``, we can't
   set a new size and it can vary throughout the life of the device.

 - For attributes which are modifiable by us and which aren't changing
   throughout the life of the object, we could use a property-based approach.

       >>> device.mtu
       1500
       # actually changing the value, not the cached value.
       >>> device.mtu = 1400
       1400



Proposed distro hierarchy
=========================

Both frameworks have a concept of Distro, each different in its way:

    - cloudinit has a ``distros`` location. There is a ``Distro`` base class,
      with abstract methods implemented by particular distros.

        Problems:

        * not DRY: many implementations have duplicate code with the base class
        * not properly encapsulated: distro-specific code executed outside the
          ``distros`` namespace.
        * lots of utilities, with low coherence between them.

    - cloudbaseinit has a ``osutils`` location. There is a ``BaseOSUtils``
      base class, with a WindowsUtils implementation.

       Problems:

           * it's a pure utilities class, leading to low coherence
             between functions.
           * it is not a namespace of OS specific functionality.
             For this, there is also ``utils.windows``.

As seen, both projects lack a namespaced location for all the OS related code.

The following architecture proposal tries to solve this issue, by having one
namespace for both general utilies related to a distro, as well as distro
specific code, which doesn't have a counterpart on other distros.

It can have the following advantages:

    * one common place for all distro interaction, with standardized
      API for each subnamespace and increased coherence.

    * avoids leaky abstractions. Distro specific code goes into ``distros``
      namespace.

    * eases testability, it is easy to provide a mock with autospeccing
      for a namespace class, such as Route.

    * Pythonic API, easy to understand and use.


The distros location is proposed, with the following structure and attributes:

    - The base class for a distro is found in ``distros.base``.

    - There are specific submodules for interaction with the OS,
      such as network, users. The submodules are part of distros namespaces,
      e.g. ``distros.windows`` should contain the modules ``network``,
      ``users`` etc.

    - More modules can be added, if we identify a group of interactions that can
      be categorized in one.

    - There should be ``general`` module, which contains general utilities that can't be moved
      in another module.

    - Each submodule has its own abstract base class, which must be implemented
      by each distro. Code reuse between distros is recommended.

    - Each submodule can expose additional behaviour that might not exist in
      the base class, if that behaviour does not make sense or if there is no
      equivalent on other platforms. But don't expose leaky abstraction, this
      specific code must be written in an abstract way, so that possible alternatives
      can be found for other distros in the mean time. This means that no ctypes
      interaction with the Windows should be exposed,
      but an object with a guaranteed interface.


      cloudinit/distros/__init__.py
                        base.py

                        freebsd/
                          __init__.py
                          network.py
                          users.py
                          general.py
                          filesystem.py                          
                        windows/
                          __init__.py
                          network.py
                          users.py
                          general.py
                       ubuntu/
                          __init__.py
                          network.py
                          ....


>>> from cloudinit.distros.base import get_distro
>>> distro = get_distro()
>>> distro.network # the actual object, not the submodule
<WindowsNetwork:/distro/network/windows>
>>> distro.users
<WindowsUsers:/distro/users/windows>
>>> distro.general
<WindowsGeneral:/distro/general/windows>


As an implementation detail, obtaining the distro object for the underlying
distro can use a combination of `platform.system`_ and `platform.linux_distribution`_.


In the following, I'll try to emphasize some possible APIs for each namespace.


Network module
--------------

    The abstract class can look like this:

        class NetworkBase(ABCMeta):

           def routes(self):
             """Get the available routes, this can be the output of
             `netstat` on Posix and ``GetIpForwardTable`` on Windows.
             Each route should be an object encapsulating the inner workings
             of each variant.

             :meth:`routes` returns an object with behaviour similar to that
             of a sequence (it could be implemented using collections.Sequence
             or something similar, as long as it guarantees an interface).
             See the description of :class:`Route` for the API of the route object.

            The following behaviour should be supported by the object returned by
            :meth:`routes`.

            def __iter__(self):
               """Support iteration."""

            def __contains__(self, item):
                """Support containment."""

            def __getitem__(self, item):
                """Support element access"""

            Some API usages:

            >>> routes = network.routes()
            >>> route_object in routes
            True
            >>> '192.168.70.14' in routes
            False
            >>> route = Route.from_route_entry(
                       "0.0.0.0         192.168.60.2    "
                       "0.0.0.0         UG        0 0          "
                       "0 eth0")
            >>> route.delete()               
             """

          def default_gateway(self):
             """Get the default gateway.

             Can be implemented in the terms of :meth:`routes`.
             """

         def interfaces(self):
             """Get the network interfaces

             This can be implemented in the same vein as :meth:`routes`, e.g.
             ``sequence(Interface(...), Interface(...), ...)``
             """

         def firewall_rules(self):
             """Get a wrapper over the existing firewall rules.

             Since this seems to be only used in Windows, it can be provided
             only in the Windows utils.
             The same behaviour as for :meth:`routes` can be used, that is:

                 >>> rules = distro.network.firewall_rules()
                 # Creating a new rule.
                 >>> rule = distro.network.FirewallRule(name=..., port=..., protocol=...)
                 # Deleting a rule
                 >>> rule.delete()
                 >>> rule in rules
                 >>> for rule in rules: print(rules)
                 >>> rule = rules[0]
                 >>> rule.name, rule.port, rule.protocol, rule.allow

             This gets rid of ``cloudbaseinit.osutils.firewall_add_rule`` and
             ``cloudbaseinit.osutils.firewall_remove_rule``.
             """

         def set_static_network_config(self, adapter_name, address, netmask,
                                       broadcast, gateway, dnsnameservers):
             """Configure a new static network.

             The :meth:``cloudinit.distros.Distro.apply_network`` should be
             removed in the favour of this method,
             which will be called by each network plugin.
             The method can be a template method, providing
             hooks for setting static DNS servers, setting static gateways or
             setting static IP addresses, which will be implemented by specific
             implementations of Distros.
             """

        def hosts(self):
             """Get the content of /etc/hosts file in a more OO approach.


             >>> hosts = distro.network.hosts()
             # Add a new entry in the hosts file, as well
             # in the object container itself
             >>> hosts.add(ipaddress, hostname, alias)
             # Delete an entry from the hosts file and from
             # the object container itself
             >>> hosts.delete(ipaddress, hostname, alias)

             This gets rid of ``cloudinit.distros.Distro.update_etc_hosts``
             and can provide support for adding a new hostname for Windows, as well.
             """

        class Route(object):
             """
             Encapsulate behaviour and state of a route.
             Something similar to Posix can be adopted, with the following API:

                  route.destination
                  route.gateway
                  route.flags
                  route.refs
                  route.use
                  route.netif -> instance of :class:`Interface` object
                  route.expire
                  route.static -> 'S' in self.flags
                  route.usable -> 'U' in self.flag

             This can use a namedtuple as a base, but this should
             be considered an implementation detail by the users
             of this class.
             """

          @classmethod
          def from_route_item(self, item):
              """
              Build a Route from a routing entry, either from
              the output of `netstat` or what will be used on Posix or
              from `GetIpForwardTable`.
              """

      class Interface(object):
            """Encapsulation for the state and behaviour of an interface.

            This method gets rid of ``cloudbaseinit.osutils.get_network_adapters``
            and with the following behaviour
            it gets rid of ``cloudinit.distros._bring_up_interface``:

                >>> interfaces = distro.network.interfaces()
                >>> interface = interfaces[0]
                >>> interface.up()
                >>> interface.down()
                >>> interface.is_up()
                # Change mtu for this interface
                >>> interface.mtu = 1400
                # Get interface mtu
                >>> interface.mtu
                1400

            If we have only the name of an interface, we should be able to
            obtain a :class:`Interface` instance from it.

            >>> interface = distro.network.Interface.from_name('eth0')
            >>> interface = distro.network.Interface.from_mac( u'00:50:56:C0:00:01')

            Each Distro specific implementation of :class:`Interface` should
            be exported in the `network` module as the `Interface` attribute,
            so that the underlying OS is completely hidden from an API point-of-view.
            """

            # alternative constructors

            @classmethod
            def from_name(cls, name):
                # return a new Interface

            @classmethod
            def from_mac(self, mac):
                # return a new Interface

            # Actual methods for behaviour

            def up(self):
                """Activate the interface."""

            def down(self):
                """Deactivate the interface."""

            def is_up(self):
                """Check if the interface is activated."""

            # Other getters and setter for what can be changed for an
            # interface, such as the mtu.

            @property
            def mtu(self):
                pass

            @mtu.setter
            def mtu(self, value):
                pass

            # Other read only attributes, such as ``.name``, ``.mac`` etc.

   .. note::

       TODO: finish this section with APis for set_hostname, _read_hostname, update_hostname


Users module
------------

The base class for this namespace can look like this


     class UserBase(ABCMeta):

         def groups(self):
             """Get all the user groups from the instance.

             Similar with network.routes() et al, that is

             >>> groups = distro.users.groups()
             sequence(Group(...), Group(....), ...)
             # create a new group
             >>> group = distro.users.Group.create(name)
             # Add new members to a group
             >>> group.add(member)
             # Remove a group
             >>> group.delete()
             # Iterate groups
             >>> list(groups)

             This gets rid of ``cloudinit.distros.Distro.create_group``,
             which creates a group and adds members to it as well and it get rids of
             ``cloudbaseinit.osutils.add_user_to_local``.
             """

       def users(self):
             """Get all the users from the instance.

             Using the same idion as for :meth:`routes` and :meth:`groups`.

             >>> users = distro.users.users()
             # containment (cloudbaseinit.osutils.user_exists)
             >>> user in users
             # Iteration
             >>> for i in user: print(user)
             """

     class User:
         """ Abstracts away user interaction.

         # Creating a new user.
         >>> User.create(username=..., password=..., ...)
         # get the home dir of an user
         >>> user.home()
         # Get the password (?)
         >>> user.password
         # Set the password
         >>> user.password = ....
         # Get an instance of an User from a name
         >>> user = distros.users.User.from_name('user')
         # Disable login password
         >>> user.disable_login_password()
         # Get ssh keys
         >>> keys = user.ssh_keys()

         Posix specific implementations might provide some method
         to operate with '/etc/sudoers' file.
         """

.. note::

   TODO: what is cloudinit.distros.get_default_user?

Packaging module
----------------

This object is a thin layer over Distro specific packaging utilities,
used in cloudinit through ``distro.Distro.package_command``.
Instead of passing strings with arguments, as it currently does,
we could have a more OO approach:

      >>> distro.packaging.install(...)

      # cloudinit provides a ``package_command`` and an ``update_package_sources`` method,
      # which is:
      #          self._runner.run("update-sources", self.package_command,
      #                   ["update"], freq=PER_INSTANCE)
      #  distro.packaging.update() can be a noop operation if it was already called
      >>> distro.packaging.update(...)

 On Windows side, this can be implemented with OneGet.


Filesystem module
-----------------

Layer over filesystem interaction specific for each OS.
Most of the uses encountered are related to the concept of devices and partitions.


class FilesystemBase(ABC):

     def devices(self):
         """Get a list of devices for this instance.

         As usual, this is abstracted through a container
         DevicesContainer([Device(...), Device(...), Device(...)])

         Where the container has the following API:

         >>> devices = distro.filesystem.devices()
         >>> devices.name, devices.type, devices.label
         >>> devices.size()
         # TODO: geometry on Windows? Define the concept better.
         >>> devices.layout()
         >>> device in devices
         >>> for device in devices: print(device)
         >>> devices.partitions()
         [DevicePartition('sda1'), DevicePartition('sda2'), ...]
         # TODO: FreeBSD has slices, which translates to partitions on
         # Windows and partitions of slices, how
         # does this translate with the current arch?


         Each DevicePartition shares a couple of methods / attributes with the Device,
         such as ``name``, ``type``, ``label``, ``size``. They have extra methods:

           >>> partition.resize()
           >>> partition.recover()
           >>> partition.mount()
           >>> with partition.mount(): # This can be noop on Windows.
                     ....

         Obtaining either a device or a partition from a string, should be done
         in the following way:

           >>> device = Device.from_name('sda')
           >>> partition = DevicePartition.from_name('sda', 1)
           >>> partition = DevicePartition.from_name('sda1')
         """

General module
--------------

Here we could have other general OS utilities: terminate, apply_locale,
set_timezone, execute_process etc. If some utilities can be grouped
after some time into a more specialized namespace, then they can be moved.


Drawbacks
=========

The only reasonable drawbacks that this proposal can have are:

  * moving all the parts from both projects will take a while.
    Since we started from the beginning knowing that cloudinit
    and cloudbaseinit codebases aren't compatible enough for a
    clean merge, this drawback might not be that huge. It's a pain
    that we must deal with as soon as possible.

  * the new API could be a source of unexpected bugs, but we should
    target a high testing coverage in order to alleviate this.



 .. _platform.system: https://docs.python.org/2/library/platform.html#platform.system 
 .. _platform.linux_distribution: https://docs.python.org/2/library/platform.html#platform.linux_distribution
