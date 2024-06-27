.. _logging:

Logging
*******

Cloud-init supports both local and remote logging configurable through
multiple configurations:

- Python's built-in logging configuration
- Cloud-init's event reporting system
- The ``cloud-init`` ``rsyslog`` module

Python logging
==============

Cloud-init uses the Python logging module, and can accept config for this
module using the standard Python ``fileConfig`` format. Cloud-init looks
for config for the logging module under the ``logcfg`` key.

.. note::

   The logging configuration is not YAML, it is Python ``fileConfig`` format,
   and is passed through directly to the Python logging module. Please use
   the correct syntax for a multi-line string in YAML.

By default, cloud-init uses the logging configuration provided in
:file:`/etc/cloud/cloud.cfg.d/05_logging.cfg`. The default Python logging
configuration writes all cloud-init events with a priority of ``WARNING``
or higher to console, and writes all events with a level of ``DEBUG`` or
higher to :file:`/var/log/cloud-init.log` and via :file:`syslog`.

Python's ``fileConfig`` format consists of sections with headings in the
format ``[title]`` and key value pairs in each section. Configuration for
Python logging must contain the sections ``[loggers]``, ``[handlers]``, and
``[formatters]``, which name the entities of their respective types that will
be defined. The section name for each defined logger, handler and formatter
will start with its type, followed by an underscore (``_``) and the name of
the entity. For example, if a logger was specified with the name ``log01``,
config for the logger would be in the section ``[logger_log01]``.

Logger config entries contain basic logging setup. They may specify a list of
handlers to send logging events to as well as the lowest priority level of
events to handle. A logger named ``root`` must be specified and its
configuration (under ``[logger_root]``) must contain a level and a list of
handlers. A level entry can be any of the following: ``DEBUG``, ``INFO``,
``WARNING``, ``ERROR``, ``CRITICAL``, or ``NOTSET``. For the ``root`` logger
the ``NOTSET`` option will allow all logging events to be recorded.

Each configured handler must specify a class under Python's ``logging``
package namespace. A handler may specify a message formatter to use, a
priority level, and arguments for the handler class. Common handlers are
``StreamHandler``, which handles stream redirects (i.e., logging to
``stderr``), and ``FileHandler`` which outputs to a log file. The logging
module also supports logging over net sockets, over http, via smtp, and
additional complex configurations. For full details about the handlers
available for Python logging, see the `python logging handlers`_ documentation.

Log messages are formatted using the ``logging.Formatter`` class, which is
configured using ``formatter`` config entities. A default format of
``%(message)s`` is given if no formatter configs are specified. Formatter
config entities accept a format string that supports variable replacements.
These may also accept a ``datefmt`` string which may be used to configure the
timestamp used in the log messages. The format variables ``%(asctime)s``,
``%(levelname)s`` and ``%(message)s`` are commonly used and represent the
timestamp, the priority level of the event and the event message. For
additional information on logging formatters see `python logging formatters`_.

.. note::

   By default, the format string used in the logging formatter are in Python's
   old style ``%s`` form. The ``str.format()`` and ``string.Template`` styles
   can also be used by using ``{`` or ``$`` in place of ``%`` by setting the
   ``style`` parameter in formatter config.

A simple (but functional) Python logging configuration for cloud-init is
below. It will log all messages of priority ``DEBUG`` or higher to both
:file:`stderr` and :file:`/tmp/my.log` using a ``StreamHandler`` and a
``FileHandler``, using the default format string ``%(message)s``: ::

  logcfg: |
   [loggers]
   keys=root,cloudinit
   [handlers]
   keys=ch,cf
   [formatters]
   keys=
   [logger_root]
   level=DEBUG
   handlers=
   [logger_cloudinit]
   level=DEBUG
   qualname=cloudinit
   handlers=ch,cf
   [handler_ch]
   class=StreamHandler
   level=DEBUG
   args=(sys.stderr,)
   [handler_cf]
   class=FileHandler
   level=DEBUG
   args=('/tmp/my.log',)

For additional information about configuring Python's logging module, please
see the documentation for `python logging config`_.

.. _logging_command_output:

Command output
==============

Cloud-init can redirect its :file:`stdout` and :file:`stderr` based on
config given under the ``output`` config key. The output of any commands run
by cloud-init and any user or vendor scripts provided will also be
included here. The ``output`` key accepts a dictionary for configuration.
Output files may be specified individually for each stage (``init``,
``config``, and ``final``), or a single key ``all`` may be used to specify
output for all stages.

The output for each stage may be specified as a dictionary of ``output`` and
``error`` keys, for :file:`stdout` and :file:`stderr` respectively, as a tuple
with :file:`stdout` first and :file:`stderr` second, or as a single string to
use for both. The strings passed to all of these keys are handled by the
system shell, so any form of redirection that can be used in bash is valid,
including piping cloud-init's output to ``tee``, or ``logger``. If only a
filename is provided, cloud-init will append its output to the file as
though ``>>`` was specified.

By default, cloud-init loads its output configuration from
:file:`/etc/cloud/cloud.cfg.d/05_logging.cfg`. The default config directs both
:file:`stdout` and :file:`stderr` from all cloud-init stages to
:file:`/var/log/cloud-init-output.log`. The default config is given as: ::

    output: { all: "| tee -a /var/log/cloud-init-output.log" }

For a more complex example, the following configuration would output the init
stage to :file:`/var/log/cloud-init.out` and :file:`/var/log/cloud-init.err`,
for :file:`stdout` and :file:`stderr` respectively, replacing anything that
was previously there. For the config stage, it would pipe both :file:`stdout`
and :file:`stderr` through :command:`tee -a /var/log/cloud-config.log`. For
the final stage it would append the output of :file:`stdout` and
:file:`stderr` to :file:`/var/log/cloud-final.out` and
:file:`/var/log/cloud-final.err` respectively. ::

    output:
        init:
            output: "> /var/log/cloud-init.out"
            error: "> /var/log/cloud-init.err"
        config: "tee -a /var/log/cloud-config.log"
        final:
            - ">> /var/log/cloud-final.out"
            - "/var/log/cloud-final.err"

Event reporting
===============

Cloud-init contains an eventing system that allows events to be emitted
to a variety of destinations.

Three configurations are available for reporting events:

- ``webhook``: POST to a web server.
- ``log``: Write to the cloud-init log at configurable log level.
- ``stdout``: Print to :file:`stdout`.

The default configuration is to emit events to the cloud-init log file
at ``DEBUG`` level.

Event reporting can be configured using the ``reporting`` key in cloud-config
user data.

Configuration
-------------

``webhook``
^^^^^^^^^^^

.. code-block:: yaml

    reporting:
      <user-defined name>:
        type: webhook
        endpoint: <url>
        timeout: <timeout in seconds>
        retries: <number of retries>
        consumer_key: <OAuth consumer key>
        token_key: <OAuth token key>
        token_secret: <OAuth token secret>
        consumer_secret: <OAuth consumer secret>

``endpoint`` is the only additional required key when specifying
``type: webhook``.

``log``
^^^^^^^

.. code-block:: yaml

    reporting:
      <user-defined name>:
        type: log
        level: <DEBUG|INFO|WARN|ERROR|FATAL>

``level`` is optional and defaults to "DEBUG".

``print``
^^^^^^^^^

.. code-block:: yaml

    reporting:
      <user-defined name>:
        type: print


Example
^^^^^^^

The follow example shows configuration for all three sources:

.. code-block:: yaml

    #cloud-config
    reporting:
      webserver:
        type: webhook
        endpoint: "http://10.0.0.1:55555/asdf"
        timeout: 5
        retries: 3
        consumer_key: <consumer_key>
        token_key: <token_key>
        token_secret: <token_secret>
        consumer_secret: <consumer_secret>
      info_log:
        type: log
        level: WARN
      stdout:
        type: print

``rsyslog`` module
==================

Cloud-init's ``cc_rsyslog`` module allows for fully customizable ``rsyslog``
configuration under the ``rsyslog`` config key. The simplest way to use the
``rsyslog`` module is by specifying remote servers under the ``remotes`` key
in ``rsyslog`` config. The ``remotes`` key takes a dictionary where each key
represents the name of an ``rsyslog`` server and each value is the
configuration for that server. The format for server config is:

- optional filter for log messages (defaults to ``*.*``)
- optional leading ``@`` or ``@@``, indicating UDP and TCP respectively
  (defaults to ``@``, for UDP)
- IPv4 or IPv6 hostname or address. IPv6 addresses must be in ``[::1]``
  format (e.g., ``@[fd00::1]:514``)
- optional port number (defaults to ``514``)

For example, to send logging to an ``rsyslog`` server named ``log_serv`` with
address ``10.0.4.1``, using port number ``514``, over UDP, with all log
messages enabled one could use either of the following.

With all options specified::

    rsyslog:
        remotes:
            log_serv: "*.* @10.0.4.1:514"

With defaults used::

    rsyslog:
        remotes:
            log_serv: "10.0.4.1"


For more information on ``rsyslog`` configuration, see
:ref:`our module reference page <mod_cc_rsyslog>`.

.. LINKS:
.. _python logging config: https://docs.python.org/3/library/logging.config.html#configuration-file-format
.. _python logging handlers: https://docs.python.org/3/library/logging.handlers.html
.. _python logging formatters: https://docs.python.org/3/library/logging.html#formatter-objects
