.. _how_to_debug:

How to debug cloud-init
***********************

There are several cloud-init :ref:`failure modes<failure_states>` that one may
need to debug. Debugging is specific to the scenario, but the starting points
are often similar:

* :ref:`I cannot log in<cannot_log_in>`
* :ref:`Cloud-init did not run<did_not_run>`
* :ref:`Cloud-init did the unexpected<did_not_do_the_thing>`
* :ref:`Cloud-init never finished running<did_not_finish_running>`

.. _cannot_log_in:

I can't log in to my instance
=============================

One of the more challenging scenarios to debug is when you don't have
shell access to your instance. You have a few options:

1. Acquire log messages from the serial console and check for any errors.

2. To access instances without SSH available, create a user with password
   access (using the user-data) and log in via the cloud serial port console.
   This only works if ``cc_users_groups`` successfully ran.

3. Try running the same user-data locally, such as in one of the
   :ref:`tutorials<tutorial_index>`. Use LXD or QEMU locally to get a shell or
   logs then debug with :ref:`these steps<did_not_do_the_thing>`.

4. Try copying the image to your local system, mount the filesystem locally
   and inspect the image logs for clues.

.. _did_not_run:

Cloud-init did not run
======================

1. Check the output of ``cloud-init status --long``

   - what is the value of the ``'extended_status'`` key?
   - what is the value of the ``'boot_status_code'`` key?

   See :ref:`our reported status explanation<reported_status>` for more
   information on the status.

2. Check the contents of :file:`/run/cloud-init/ds-identify.log`

   This log file is used when the platform that cloud-init is running on
   :ref:`is detected<boot-Detect>`. This stage enables or disables cloud-init.

3. Check the status of the services

   .. code-block::

      systemctl status cloud-init-local.service cloud-init.service\
         cloud-config.service cloud-final.service

   Cloud-init may have started to run, but not completed. This shows how many,
   and which, cloud-init stages completed.

.. _did_not_do_the_thing:

Cloud-init ran, but didn't do what I want it to
===============================================

1. If you are using cloud-init's user data
   :ref:`cloud config<user_data_formats-cloud_config>`, make sure
   to :ref:`validate your user data cloud config<check_user_data_cloud_config>`

2. Check for errors in ``cloud-init status --long``

   - what is the value of the ``'errors'`` key?
   - what is the value of the ``'recoverable_errors'`` key?

   See :ref:`our guide on exported errors<exported_errors>` for more
   information on these exported errors.

3. For more context on errors, check the logs files:

   - :file:`/var/log/cloud-init.log`
   - :file:`/var/log/cloud-init-output.log`

   Identify errors in the logs and the lines preceding these errors.

   Ask yourself:

   - According to the log files, what went wrong?
   - How does the cloud-init error relate to the configuration provided
     to this instance?
   - What does the documentation say about the parts of the configuration that
     relate to this error? Did a configuration module fail?
   - What :ref:`failure state<failure_states>` is cloud-init in?


.. _did_not_finish_running:

Cloud-init never finished running
=================================

There are many reasons why cloud-init may fail to complete. Some reasons are
internal to cloud-init, but in other cases, cloud-init failure to
complete may be a symptom of failure in other components of the
system, or the result of a user configuration.

External reasons
----------------

- Other services failed or are stuck.
- Bugs in the kernel or drivers.
- Bugs in external userspace tools that are called by ``cloud-init``.

Internal reasons
----------------

- A command in ``bootcmd`` or ``runcmd`` that never completes (e.g., running
  :command:`cloud-init status --wait` will deadlock).
- Configurations that disable timeouts or set extremely high timeout values.

To start debugging
------------------

1. Check ``dmesg`` for errors:

   .. code-block::

      dmesg -T | grep -i -e warning -e error -e fatal -e exception

2. Investigate other systemd services that failed

   .. code-block::

      systemctl --failed

3. Check the output of ``cloud-init status --long``

   - what is the value of the ``'extended_status'`` key?
   - what is the value of the ``'boot_status_code'`` key?

   See :ref:`our guide on exported errors<reported_status>` for more
   information on these exported errors.

4. Inspect running services :ref:`boot stage<boot_stages>`:

   .. code-block::

      $ systemctl list-jobs --after
      JOB UNIT                                             TYPE  STATE
      150 cloud-final.service                              start waiting
      └─      waiting for job 147 (cloud-init.target/start)   -     -
      155 blocking-daemon.service                               start running
      └─      waiting for job 150 (cloud-final.service/start) -     -
      147 cloud-init.target                                start waiting

      3 jobs listed.


   In the above example we can see that ``cloud-final.service`` is
   waiting and is ordered before ``cloud-init.target``, and that
   ``blocking-daemon.service`` is currently running and is ordered
   before ``cloud-final.service``. From this output, we deduce that cloud-init
   is not complete because the service named ``blocking-daemon.service`` hasn't
   yet completed, and that we should investigate ``blocking-daemon.service``
   to understand why it is still running.

5. Use the PID of the running service to find all running subprocesses.
   Any running process that was spawned by cloud-init may be blocking
   cloud-init from continuing.

   .. code-block::

      pstree <PID>

   Ask yourself:

   - Which process is still running?
   - Why is this process still running?
   - How does this process relate to the configuration that I provided?

6. For more context on errors, check the logs files:

   - :file:`/var/log/cloud-init.log`
   - :file:`/var/log/cloud-init-output.log`

   Identify errors in the logs and the lines preceding these errors.

   Ask yourself:

   - According to the log files, what went wrong?
   - How does the cloud-init error relate to the configuration provided to this
     instance?
   - What does the documentation say about the parts of the configuration that
     relate to this error?
