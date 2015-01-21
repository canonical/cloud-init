=====================
Hacking on cloud-init
=====================

To get changes into cloud-init, the process to follow is:

* If you have not already, be sure to sign the CCA:

  - `Canonical Contributor Agreement`_

* fork from github, create a branch and make your changes
  - ``git clone https://github.com/cloud-init/cloud-init.git``
  - ``cd cloud-init``
  - ``echo hack``

* Check test and code formatting / lint and address any issues:

  - ``tox``

* Commit / ammend your changes
  Before review, make good commit messages with one line summary
  followed by empty line followed by expanded comments.
  - ``git commit``

* Push to branch to github:

  - ``git push``

* Make a pull request.

Then, someone on cloud-init team.

Feel free to ping and/or join #cloud-init on freenode (irc) if you have any questions.

.. _Canonical Contributor Agreement: http://www.canonical.com/contributors
.. _Scott Moser: https://launchpad.net/~smoser
.. _Joshua Harlow: https://launchpad.net/~harlowja
