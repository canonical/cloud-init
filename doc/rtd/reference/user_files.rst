.. _user_files:

Log files
*********

.. _log_files:

``cloud-init`` logs to multiple files:

- :file:`/run/cloud-init/cloud-init-generator.log`: Early boot; useful to
  understand why cloud-init didn't run.
- :file:`/run/cloud-init/ds-identify.log`: Early boot; useful to understand
  why cloud-init didn't run or why it detected an unexpected platform.
- :file:`/var/log/cloud-init.log`: The primary log file. Verbose, but useful.
- :file:`/var/log/cloud-init-output.log`: Captures the output from each stage.
  Output from user scripts goes here.

Logs are appended to the files in :file:`/var/log`: files may contain logs
from multiple boots.
