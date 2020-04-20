*******
Logging
*******
Cloud-init supports both local and remote logging configurable through python's
built-in logging configuration and through the cloud-init rsyslog module.

Command Output
==============
Cloud-init can redirect its stdout and stderr based on config given under the
``output`` config key. The output of any commands run by cloud-init and any
user or vendor scripts provided will also be included here. The ``output`` key
accepts a dictionary for configuration. Output files may be specified
individually for each stage (``init``, ``config``, and ``final``), or a single
key ``all`` may be used to specify output for all stages.

The output for each stage may be specified as a dictionary of ``output`` and
``error`` keys, for stdout and stderr respectively, as a tuple with stdout
first and stderr second, or as a single string to use for both. The strings
passed to all of these keys are handled by the system shell, so any form of
redirection that can be used in bash is valid, including piping cloud-init's
output to ``tee``, or ``logger``. If only a filename is provided, cloud-init
will append its output to the file as though ``>>`` was specified.

By default, cloud-init loads its output configuration from
``/etc/cloud/cloud.cfg.d/05_logging.cfg``. The default config directs both
stdout and stderr from all cloud-init stages to
``/var/log/cloud-init-output.log``. The default config is given as ::

    output: { all: "| tee -a /var/log/cloud-init-output.log" }

For a more complex example, the following configuration would output the init
stage to ``/var/log/cloud-init.out`` and ``/var/log/cloud-init.err``, for
stdout and stderr respectively, replacing anything that was previously there.
For the config stage, it would pipe both stdout and stderr through ``tee -a
/var/log/cloud-config.log``. For the final stage it would append the output of
stdout and stderr to ``/var/log/cloud-final.out`` and
``/var/log/cloud-final.err`` respectively. ::

    output:
        init:
            output: "> /var/log/cloud-init.out"
            error: "> /var/log/cloud-init.err"
        config: "tee -a /var/log/cloud-config.log"
        final:
            - ">> /var/log/cloud-final.out"
            - "/var/log/cloud-final.err"

Python Logging
--------------
Cloud-init uses the python logging module, and can accept config for this
module using the standard python fileConfig format. Cloud-init looks for
config for the logging module under the ``logcfg`` key.

.. note::
    the logging configuration is not yaml, it is python ``fileConfig`` format,
    and is passed through directly to the python logging module. please use the
    correct syntax for a multi-line string in yaml.

By default, cloud-init uses the logging configuration provided in
``/etc/cloud/cloud.cfg.d/05_logging.cfg``. The default python logging
configuration writes all cloud-init events with a priority of ``WARNING`` or
higher to console, and writes all events with a level of ``DEBUG`` or higher
to ``/var/log/cloud-init.log`` and via syslog.

Python's fileConfig format consists of sections with headings in the format
``[title]`` and key value pairs in each section. Configuration for python
logging must contain the sections ``[loggers]``, ``[handlers]``, and
``[formatters]``, which name the entities of their respective types that will
be defined. The section name for each defined logger, handler and formatter
will start with its type, followed by an underscore (``_``) and the name of
the entity. For example, if a logger was specified with the name ``log01``,
config for the logger would be in the section ``[logger_log01]``.

Logger config entries contain basic logging set up. They may specify a list of
handlers to send logging events to as well as the lowest priority level of
events to handle. A logger named ``root`` must be specified and its
configuration (under ``[logger_root]``) must contain a level and a list of
handlers. A level entry can be any of the following: ``DEBUG``, ``INFO``,
``WARNING``, ``ERROR``, ``CRITICAL``, or ``NOTSET``. For the ``root`` logger
the ``NOTSET`` option will allow all logging events to be recorded.

Each configured handler must specify a class under the python's ``logging``
package namespace. A handler may specify a message formatter to use, a
priority level, and arguments for the handler class. Common handlers are
``StreamHandler``, which handles stream redirects (i.e. logging to stderr),
and ``FileHandler`` which outputs to a log file. The logging module also
supports logging over net sockets, over http, via smtp, and additional complex
configurations. For full details about the handlers available for python
logging, please see the documentation for `python logging handlers`_.

Log messages are formatted using the ``logging.Formatter`` class, which is
configured using ``formatter`` config entities. A default format of
``%(message)s`` is given if no formatter configs are specified. Formatter
config entities accept a format string which supports variable replacements.
These may also accept a ``datefmt`` string which may be used to configure the
timestamp used in the log messages. The format variables ``%(asctime)s``,
``%(levelname)s`` and ``%(message)s`` are commonly used and represent the
timestamp, the priority level of the event and the event message. For
additional information on logging formatters see `python logging formatters`_.

.. note::
    by default the format string used in the logging formatter are in python's
    old style ``%s`` form. the ``str.format()`` and ``string.Template`` styles
    can also be used by using ``{`` or ``$`` in place of ``%`` by setting the
    ``style`` parameter in formatter config.

A simple, but functional python logging configuration for cloud-init is below.
It will log all messages of priority ``DEBUG`` or higher both stderr and
``/tmp/my.log`` using a ``StreamHandler`` and a ``FileHandler``, using
the default format string ``%(message)s``::

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

For additional information about configuring python's logging module, please
see the documentation for `python logging config`_.

Rsyslog Module
--------------
Cloud-init's ``cc_rsyslog`` module allows for fully customizable rsyslog
configuration under the ``rsyslog`` config key. The simplest way to
use the rsyslog module is by specifying remote servers under the ``remotes``
key in ``rsyslog`` config. The ``remotes`` key takes a dictionary where each
key represents the name of an rsyslog server and each value is the
configuration for that server. The format for server config is:

 - optional filter for log messages (defaults to ``*.*``)
 - optional leading ``@`` or ``@@``, indicating udp and tcp respectively
   (defaults to ``@``, for udp)
 - ipv4 or ipv6 hostname or address. ipv6 addresses must be in ``[::1]``
   format, (e.g. ``@[fd00::1]:514``)
 - optional port number (defaults to ``514``)

For example, to send logging to an rsyslog server named ``log_serv`` with
address ``10.0.4.1``, using port number ``514``, over udp, with all log
messages enabled one could use either of the following.

With all options specified::

    rsyslog:
        remotes:
            log_serv: "*.* @10.0.4.1:514"

With defaults used::

    rsyslog:
        remotes:
            log_serv: "10.0.4.1"


For more information on rsyslog configuration, see :ref:`cc_rsyslog`.

.. _python logging config: https://docs.python.org/3/library/logging.config.html#configuration-file-format
.. _python logging handlers: https://docs.python.org/3/library/logging.handlers.html
.. _python logging formatters: https://docs.python.org/3/library/logging.html#formatter-objects
.. vi: textwidth=78
