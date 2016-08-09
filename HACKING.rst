=====================
Hacking on cloud-init
=====================

This document describes how to contribute changes to cloud-init.

Do these things once
--------------------

* If you have not already, be sure to sign the CCA:

  - `Canonical Contributor Agreement`_

* Clone the `LaunchPad`_ repository:

    git clone YOUR_USERNAME@git.launchpad.net:cloud-init
    cd cloud-init

  If you would prefer a bzr style `git clone lp:cloud-init`, see
  the `Instructions on LaunchPad`_ for more information.

* Create a new remote pointing to your personal LaunchPad
  repository::

    git remote add YOUR_USERNAME YOUR_USERNAME@git.launchpad.net:~YOUR_USERNAME/cloud-init

.. _Canonical Contributor Agreement: http://www.canonical.com/contributors

Do these things for each feature or bug
---------------------------------------

* Create a new topic branch for your work::

    git checkout -b my-topic-branch

.. _Instructions on launchpad: https://help.launchpad.net/Code/Git

* Make and commit your changes (note, you can make multiple commits,
  fixes, more commits.)::

    git commit

* Check pep8 and test, and address any issues::

    make test pep8

* Push your changes to your personal LaunchPad repository::

    git push -u YOUR_USERNAME my-topic-branch

* Use your browser to create a merge request:

  - Open the branch on `LaunchPad`_

    - It will typically be at
      ``https://code.launchpad.net/~YOUR_USERNAME/cloud-init/+git/cloud-init/+ref/BRANCHNAME``
      for example
      https://code.launchpad.net/~larsks/cloud-init/+git/cloud-init/+ref/feature/move-to-git

  - Click 'Propose for merging`
  - Select ``cloud-init`` as the target repository
  - Select ``master`` as the target reference path

Then, someone on cloud-init-dev (currently `Scott Moser`_ and `Joshua
Harlow`_) will review your changes and follow up in the merge request.

Feel free to ping and/or join ``#cloud-init`` on freenode (irc) if you
have any questions.

.. _Launchpad: https://launchpad.net
.. _Scott Moser: https://launchpad.net/~smoser
.. _Joshua Harlow: https://launchpad.net/~harlowja
