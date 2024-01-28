cloud-init: Summit 2019
***********************

.. note::

   This article was written by Joshua Powers and `originally published`_ on 21
   October 2019. It is shared here `under license`_ with no changes.

.. image:: https://assets.ubuntu.com/v1/e0319f90-2019_market.jpg
   :alt: Seattle market
   :align: center

Last month the cloud-init development team from Canonical ran our third annual
two-day summit. Attendees included cloud developers from Amazon, Cisco,
Microsoft, Google, and Oracle, as well as the maintainers of cloud-init from
Amazon Linux, SUSE, Red Hat, and Ubuntu.

The purpose of this two-day event is to meet with contributors, demo recent
developments, present future plans, resolve outstanding issues, and collect
additional feedback on the past year.

Like last year, the even was held in Seattle, Washington. A special thanks goes
to Amazon for providing breakfast and lunch while hosting us!

Topics and Decisions
====================

Here are summary of some of the topics discussed during the sprint:

* **New Security Process**: I proposed a process by which security issues would
  be reported to the project, how they would be evaluated, fixed, and
  eventually disclosed. While this is not fully complete, the process has
  already been `used once`_ to evaluate what turned out to be non-security
  issues.
* **Boot Performance**: Ryan started the second day off talking about the boot
  performance analysis that he is conducted. He has proposed an initial branch
  with changes to help many clouds improve their time to SSH. While this work
  will involve effort across platforms, kernels, distros, and cloud-init, we
  can already start to make changes to cloud-init.
* **GitHub Transition**: We are moving the project to GitHub in an effort to
  continue to gather contributions and improve our merge proposal process. We
  have some early testing and CI branches ready to go. We are waiting on some
  open questions around the CLA and mirroring back to Launchpad to continue the
  move.
* **Python Support**: The last release of cloud-init in 2019 is the final
  version to support python 2.7. We will cut a branch for future bug fixes.
  After that master will now support Python 3.4 going forward. A future
  discussion around how to move the Python 3 version is needed. See the
  `mailing list post`_ for more details.
* **Red Hat Support**: Edwardo gave a presentation on Red Hat’s process around
  cloud-init. He showed the versions they are on and what they do when a new
  release comes out.

Working Sessions
================

During the summit, we took time to have merge review and bug squashing time.
During this time, attendees came with outstanding bugs to discuss possible
fixes as well as go through outstanding merge requests and get live reviews.

.. image:: https://assets.ubuntu.com/v1/d774b249-2019_amazon.jpg
   :alt: Another talk
   :align: center

Thank you
=========

As always a huge thank you to the community for attending! The summit was a
great time to see many contributors face-to-face as well as collect feedback
for cloud-init development.

`Notes of both days`_ can be found on the cloud-init mailing list. There you
will find additional details about what I have described above and much more.

Finally, if you are interested in following or getting involved in cloud-init
development check out #cloud-init on Freenode or subscribe to the
`cloud-init mailing list`_.

.. LINKS:
.. _originally published: https://powersj.io/posts/cloud-init-summit19/
.. _under license: https://creativecommons.org/licenses/by/4.0/
.. _used once: https://lists.launchpad.net/cloud-init/msg00228.html
.. _mailing list post: https://lists.launchpad.net/cloud-init/msg00227.html
.. _Notes of both days: https://lists.launchpad.net/cloud-init/msg00226.html
.. _cloud-init mailing list: https://launchpad.net/~cloud-init
