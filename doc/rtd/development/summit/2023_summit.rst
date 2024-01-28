cloud-init: Summit 2023
***********************

After a three-year hiatus the two-day cloud-init summit finally resumed in
August, giving Canonical a chance to reconnect with the community in person,
and to realign on the direction and goals of the project.

.. figure:: https://assets.ubuntu.com/v1/d8ed72fb-2023_image1.jpg
    :alt: Man running along a trail through the forest near the venue
    :align: center

    Enjoying a jog through the beautiful forest around the Microsoft Redmond
    campus!

The event was generously hosted by Microsoft this year at their Redmond campus
in Seattle, Washington, and we are grateful to the Microsoft community members
"on the ground" who coordinated with Canonical's cloud-init development team to
help organise and run the event. Big thanks go as well to the Canonical
community team for helping us to set up the event site, as well as for their
support and guidance with all the planning involved.

As in previous years, the summit was a great opportunity for cloud-init
contributors to get together and discuss the most recent developments in the
project, provide demos of new features, resolve outstanding issues, and shape
the future development direction of the project. It was wonderful to see some
"old" faces again after such a long time, as well as getting to meet some of
our newer contributors in person.

The first hybrid summit
=======================

This summit was organised as a hybrid event for the first time, and despite
some initial uncertainties about how to implement that, it worked very well.
In-person attendees included developers and contributors from Microsoft,
Google, Amazon, Oracle, openSUSE and we had remote presentations provided by
FreeBSD and AlpineLinux maintainers.

In addition to our in-person gathering, we also had lively participation from
our remote attendees from around the world. With this hybrid format allowing
attendance from community members who might not otherwise have been able to
take part, this is a format that we’ll want to carry forward to next year to
open the event to the widest possible audience.

Special thanks go to Canonical for sponsoring the dinner! It was a great chance
to build community interactions "after hours", with topics ranging far and
wide. Overall, it was a perfect opportunity to dig into industry dynamics that
influence cloud-init engagement.

.. image:: https://assets.ubuntu.com/v1/2687e23a-2023_image3.jpg
    :alt: The in-person participants enjoying the group dinner
    :align: center

Highlights of the discussions
=============================

Thanks to all our presenters; Mina Galic (FreeBSD) and Dermot Bradley
(AlpineLinux), Chris Patterson (Microsoft) James Falcon, Brett Holman,
Catherine Redfield, Alberto Contreras, Sally Makin, John Chittum, Daniel
Bungert and Chad Smith. You really helped to make this event a success.

Presentation take-aways
-----------------------

* **Integration-testing tour/demo**: James showed how Canonical uses our
  integration tests and pycloudlib during SRU verification, and demonstrated
  how we think other clouds should be involved in standard evaluation of
  cloud-init releases before publication.

  There was interest in leveraging this testing at openSUSE, Amazon Linux and
  possibly Microsoft’s Mariner; they may be looking to extend our framework for
  their release testing. Our homework from this is improved developer docs on
  extending integration tests for other distributions.

  Azure are looking to invest in distribution-agnostic integration test
  frameworks and want to knowledge-share with the cloud-init community on that.

* **Security-policy for cloud-init CVE handling**: Our community would like
  Canonical to provide more context during the embargo period on CVEs about the
  mitigation steps required. This is especially the case in any downstream
  packaging, to allow downstream package maintainers more time to prepare.

* **Cloud platforms want/like strict schema validation** and errors on invalid
  user-data/config. They also requested more visibility into any warnings
  surfaced by cloud-init with simple tools so that they can avoid costly "log
  spelunking".

  This aligns well with Brett’s ongoing roadmap work to raise warnings from the
  CLI and some of the strict JSON schema validation on network-config and user
  data/vendor data.

* Good lessons from both AlpineLinux (Dermot Bradley), who investigated SSH
  alternatives like dropbearSSH and tinySSH, and FreeBSD (Mina Galić), who
  reported on the development and publishing process and on finding better ways
  for FreeBSD and Alpine to engage with clouds, so they can get sponsorship of
  open source images with cloud-init hosted in AWS.

.. image:: https://assets.ubuntu.com/v1/5640b4ed-2023_image2.jpg
    :alt: Overview of the meeting room, with the remote-attending participants
    :align: center

Round-table discussions
-----------------------

* **Boot-speed**: The discussion hosted by Catherine, Alberto and Chad
  confirmed that our ongoing boot speed work is critical to clouds and
  cloud-customers, who continue to gauge boot speed based on wall time to SSH
  into the instance.

  This is a more critical measurement than the time to all services being up.
  In our discussion, we received feedback that every millisecond counts. We
  also learned that there is hesitation about moving to precompiled languages
  such as Go, due to the potential image size impacts, or Rust, due to the
  somewhat limited platform support.

  Partners are also looking for `cloud-init analyze` to report on external
  systemd-related impacts (such as `NetworkManager-wait-online.service` or
  `systemd-network-wait-online.service` delays) due to external units/services
  that affect boot.

* **Review of our Python support matrix** for all downstreams, with the goal of
  Python 3.6 version deprecation. Due to ongoing downstream support needs, we
  are looking to retain Python 3.6 support until March 2024.

* **Shared test frameworks**: Azure intends to invest in integration testing
  with the cloud-init community, to develop distribution-agnostic best
  practices for verification of distribution releases, and boot-speed and image
  health analysis. If there are ways we want to collaborate on generalised
  testing and verification of images, they may provide some development toward
  this cause.

Breakout sessions
-----------------

* **Private reviews of partner engagements** with Oracle and AWS, and Fabio
  Martins, Kyler Horner, and James to prioritise ongoing work and plan for the
  future development of IPv6-only datasource support - as well as other
  features.

* **Brett and openSUSE’s Robert Schweikert** worked through downstream patch
  review with the intent of merging many openSUSE patches upstream. Amazon
  Linux has a couple of downstream patches that they may want to upstream as
  well.

Conclusions
===========

This two-day event gave us a fantastic chance to take the pulse of the
cloud-init project. It’s given us a healthy understanding of areas in which we
can better serve the community and how we can continue to build momentum.

Meeting face-to-face to reflect our cloud-init plans with the community helped
confirm interest in some of the usability features we are developing, such as
better error and warning visibility and improving boot speed in cloud-init.
There is plenty of enthusiasm for continued collaboration on improved testing
and verification that all distributions and clouds can leverage.

We also appreciated the opportunity to get valuable feedback on our
documentation, our communication, and our security processes. We’ve also
discussed and gained input into better practices we can adopt through GitHub
automation, workflows that automate pull request digests, and upstream test
matrix coverage for downstreams (beside Ubuntu). All of these things will help
us to maintain the momentum of the cloud-init project and ensure that we are
best serving the needs of our community.

Thank you!
==========

This event could not have taken place without the hard work and preparation of
all our presenters, organisers, and the voices of our community members in
attendance. So, thank you again to everyone who participated, and we very much
hope to see you again at the next cloud-init summit!

Notes of both days can be found on the `cloud-init mailing list`_, and also
are `hosted in our GitHub`_ repository. There you will find additional details
about each topic and related discussions.

Finally, if you are interested in following or getting involved in cloud-init
development check out #cloud-init on Libera.chat or subscribe to the cloud-init
mailing list.

.. LINKS
.. _cloud-init mailing list: https://lists.launchpad.net/cloud-init/msg00460.html
.. _hosted in our GitHub: https://github.com/canonical/cloud-init/blob/main/doc/summit/2023_summit_shared_notes.md
