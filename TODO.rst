==============================================
Things that cloud-init may do (better) someday
==============================================

- Consider making ``failsafe`` ``DataSource``
  - sets the user password, writing it to console

- Consider a ``previous`` ``DataSource``, if no other data source is
  found, fall back to the ``previous`` one that worked.
- Rewrite ``cloud-init-query`` (currently not implemented)
- Possibly have a ``DataSource`` expose explicit fields:

  - instance-id
  - hostname
  - mirror
  - release
  - ssh public keys

- Remove the conversion of the ubuntu network interface format conversion
  to a RH/fedora format and replace it with a top level format that uses
  the netcf libraries format instead (which itself knows how to translate
  into the specific formats). See for example `netcf`_ which seems to be
  an active project that has this capability.
- Replace the ``apt*`` modules with variants that now use the distro classes
  to perform distro independent packaging commands (wherever possible).
- Replace some the LOG.debug calls with a LOG.info where appropriate instead
  of how right now there is really only 2 levels (``WARN`` and ``DEBUG``)
- Remove the ``cc_`` prefix for config modules, either have them fully
  specified (ie ``cloudinit.config.resizefs``) or by default only look in
  the ``cloudinit.config`` namespace for these modules (or have a combination
  of the above), this avoids having to understand where your modules are
  coming from (which can be altered by the current python inclusion path)
- Instead of just warning when a module is being ran on a ``unknown``
  distribution perhaps we should not run that module in that case? Or we might
  want to start reworking those modules so they will run on all
  distributions? Or if that is not the case, then maybe we want to allow
  fully specified python paths for modules and start encouraging
  packages of ``ubuntu`` modules, packages of ``rhel`` specific modules that
  people can add instead of having them all under the  cloud-init ``root``
  tree? This might encourage more development of other modules instead of
  having to go edit the cloud-init code to accomplish this.

.. _netcf: https://fedorahosted.org/netcf/
