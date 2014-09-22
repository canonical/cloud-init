=====================
Hacking on cloud-init
=====================

To get changes into cloud-init, the process to follow is:

* If you have not already, be sure to sign the CCA:

  - `Canonical Contributor Agreement`_

* Get your changes into a local bzr branch.
  Initialize a repo, and checkout trunk (init repo is to share bzr info across multiple checkouts, its different than git):

  - ``bzr init-repo cloud-init``
  - ``bzr branch lp:cloud-init trunk.dist``
  - ``bzr branch trunk.dist my-topic-branch``

* Commit your changes (note, you can make multiple commits, fixes, more commits.):

  - ``bzr commit``

* Check pep8 and test, and address any issues:

  - ``make test pep8``

* Push to launchpad to a personal branch:

  - ``bzr push lp:~<YOUR_USERNAME>/cloud-init/<BRANCH_NAME>``

* Propose that for a merge into lp:cloud-init via web browser.

  - Open the branch in `Launchpad`_

    - It will typically be at ``https://code.launchpad.net/<YOUR_USERNAME>/<PROJECT>/<BRANCH_NAME>``
    - ie. https://code.launchpad.net/~smoser/cloud-init/mybranch

* Click 'Propose for merging'
* Select 'lp:cloud-init' as the target branch

Then, someone on cloud-init-dev (currently `Scott Moser`_ and `Joshua Harlow`_) will 
review your changes and follow up in the merge request.

Feel free to ping and/or join #cloud-init on freenode (irc) if you have any questions.

.. _Launchpad: https://launchpad.net
.. _Canonical Contributor Agreement: http://www.canonical.com/contributors
.. _Scott Moser: https://launchpad.net/~smoser
.. _Joshua Harlow: https://launchpad.net/~harlowja
