# Cloud-init summit digest

Hello cloud-init community!

We wanted to provide a summary of the notes from the August 2023 cloud-init
Summit in a more digestible fashion so that those without Google accounts can
also review the meeting notes to get up to speed on the conversations and
topics covered at the event.

We will soon link event highlights, presentation materials and maybe a couple
of videos of presentations on our documentation site at:
https://cloudinit.readthedocs.io/en/latest/development/summit.html

For those who weren't able to attend, this meeting was Canonical's first
hybrid attendance summit, with both physical and virtual participants.
The running notes are transcribed from a shared Google document to provide
simpler access. The original shared notes
[are also available](https://docs.google.com/document/d/1unINhucL6wcn7xqIL6IIAik8nwuacq5d-u0e3K0437s).

## Our thanks

First of all, many thanks to our sponsors for the event:

- Microsoft Azure folks for providing meeting rooms, video conferencing and
  lunches/snacks for both days at their Redmond Campus.
- Canonical for sponsoring travel and the group dinner on Wednesday night.
- The presenters who made this event possible by providing excellent content,
  demos and discussions.

## Topic schedule

Below is an ordered list of scheduled topics that were covered, and the
presenters who led those efforts:

### Summit day 1

1. **Presentation** Recent Features / Roadmap / Q & A: Brett Holman (Canonical)
1. **Presentation** Intro to our new technical author: Sally Makin (Canonical)
1. **Presentation** FreeBSD State of the Union: Mina Galic (FreeBSD Foundation)
1. **Presentation** Status of cloud-init versions and support in various
   distribution downstreams: Chad Smith (Canonical)
1. **Roundtable** Python version support matrix and deprecation plan: James
   Falcon (Canonical)
1. **Roundtable** Status of distribution downstream patches: Brett Holman
   (Canonical)
1. **Roundtable** Status of testing and/or publication of cloud-init in various
   OSes: Chad Smith (Canonical)
1. **Demo** Integration testing updates for pycloudlib: James Falcon
1. **Presentation** Security policy overview: Chad Smith
1. **Demo** Ubuntu live installer: Dan Bungert (Canonical)
1. **Demo** Canonical CPC, test framework John Chittum (Canonical public cloud
   Manager)
1. **Demo** Cloud-init schema validation and validation service: Alberto
   Contreras (Canonical)

### Summit day 2

13. **Presentation** Cloud-init and Alpine: Dermot Bradley (AlpineLinux)
1. **Presentation** Documentation overhaul and policy for cloud-init (Sally
   Makin)
1. **Roundtable** Boot speed in cloud-init: Chad Smith, Alberto Contreras,
   Catherine Redfield (Canonical)
1. **Demo** instance-id in LXD: James Falcon (Canonical)
1. **Demo** Cloud testing tools in the cloud-init ecosystem: Chris Patterson,
   Ahn Vo (Microsoft)
1. **Roundtable** Rotten tomatoes: what can the cloud-init project do better?
1. **Discussion** ISC-dhclient deprecation status: Brett Holman
1. **Breakout sessions** With Oracle and AWS: Fabio Martins and Kyler Horner
   (Canonical)


Many thanks to all of our presenters and participants!

Below is the wall-of-text transcribed from our shared meeting notes. A response
will also be provided to this thread when we have published our distilled trip
report to our documentation at https://cloudinit.readthedocs.io.

Happy hacking,

Chad Smith

cloud-init upstream developer





# cloud-init summit August 2023 notes

## Attendees

The cloud-init summit had representation both in-person and remotely from the
following community members:

| Name               | Company/Project/Role               | Attendance        |
| ------------------ | ---------------------------------- | ----------------- |
| Alberto Contreras  | Canonical / Server-CPC / SW Eng    | In person         |
| Brett Holman       | Canonical / Server / SW Eng        | In person         |
| Calvin Mwadime     | Canonical / Server-CPC / SW Eng    | Remote            |
| Catherine Redfield | Canonical / Server-CPC / SW Eng    | Remote            |
| Chad Smith         | Canonical / Server / SW Eng        | In person         |
| Christian Ehrhardt | Canonical / Server / Manager       | Remote            |
| Daniel Bungert     | Canonical / Foundations / SW Eng   | In person         |
| Fabio Martins      | Canonical / Support Eng            | In person         |
| James Falcon       | Canonical / Server / SW Eng        | In person         |
| John Chittum       | Canonical / CPC / Manager          | In person         |
| Kyler Horner       | Canonical / Support Eng / TAM      | In person         |
| Sally Makin        | Canonical / Server / Documentation | Remote            |
| Deepika Rajadesingan | Oracle                           | Remote            |
| Eric Mackay        | Oracle                             | In person         |
| Guillaume Beaudoin | Oracle / Platform images           | In person         |
| Harsha Koonaparaju | Oracle                             | Remote            |
| Paul Graydon       | Oracle                             | In person         |
| Rajesh Harekal     | Oracle                             | Remote            |
| Anh Vo             | Microsoft / Azure Linux            | In person         |
| Chris Patterson    | Microsoft                          | In person         |
| Lexi Nadolski      | Microsoft                          | Remote            |
| Minghe Ren         | Microsoft                          | In person         |
| Moustafa Moustafa  | Microsoft                          | Remote            |
| Nell Shamrell-Harrington | Microsoft / Rust Foundation  | In person         |
| Peyton Robertson   | Microsoft                          | In person         |
| Huijuan Zhao       | Redhat                             | Remote            |
| Wei Shi            | Redhat / CentOS                    | Remote            |
| Yaju Cao           | Redhat                             | Remote            |
| Bastian Blank      | Amazon / Debian                    | In person         |
| Frederick Lefebvre | ASW / Amazon Linux                 | In Person         |
| Noah Meyerhans     | Amazon                             | In Person         |
| Andrew Jorgensen   | GCP / Guest Ecosystem / Staff Eng  | Both              |
| Justin Haynes      | GCP                                | In person         |
| Mina Galić         | FreeBSD Foundation / maintainer    | Remote            |
| Dermot Bradly      | AlpineLinux / Maintainer           | Remote            |
| Robert Schweikert  | SUSE / Distinguished eng           | In person         |
| Matthew Penington  | AWS / EC2 Commercial Linux/SDE     | In person         |
| Matt Chidambaram   | Cloud Migration/ DevOs SRE         | Remote            |
| Kristjan Onu       | National Research Council Canada   | Remote            |

## Day 1 running notes, per session

### Presentation: recent features / roadmap / Q and A

Presented by: Brett Holman (Canonical)

* [Slides: cloud-init summit intro](https://docs.google.com/presentation/d/1i4ufgXcfQ9rQLIfgeqMMkr6w5Bpu-RrhAaPTxo0BofM/edit?usp=sharing)
* CVEs, code changes, new clouds added and config modules provided
* Versioning policy: time-based versions `YY.<calendar_quarter_of_release>`
e.g. 22.1, 22.2 etc
* Feedback / discussion:
  * NoahM: New docs -- I can now quickly navigate to solutions

### Presentation: Intro to our new Technical Author

Presented by: Sally Makin (Canonical)

* [Slides](https://docs.google.com/presentation/d/12ZFawGOxlzg_J5bYtcE_anYbNFiFVHb2xFTyOQy9rio/edit?usp=sharing)
* [Recording](https://drive.google.com/file/d/1v23sXtyo4AILTyqRIH2CtVkl5zVgi7oY/view?usp=sharing)

### Presentation: FreeBSD State of the Union

Presented by: Mina Galic (FreeBSD Foundation)

* [Talk notes](https://scratchpad.pkgbase.live/q0Ajf3LtTaqXXH0v99Sykg?view#)
* At the start of this project there were 130 failing tests on BSD.
* Since FreeBSD 13.2 release, unit tests are being fixed upstream.
* Biggest issues:
  * Not being able to test on your target platform has been a real challenge.
  * Trying to ensure we have fully integrated cloud-init CI within FreeBSD's
    test infrastructure.
* Looking to get cloud vendors to provide official FreeBSD images with
  cloud-init installed.
* Mina has been driving integration tests working on LXD platform for ease of
  free and local integration test runs.
  * LXD Virtio vSocket support complexities are causing trouble for BSD due to
    the lack of a vSocket module.
   * BSD has a Hyper-V module, but no vSocket.
   * Spent time trying to convert Hyper-V socket module to support vSocket.
* Network refactors that resulted in InfiniBand support for cloud-init. Tabled
  that effort due to lack of resources, testing and expertise.
  * What is missing from BSD for network refactor:
    * Missing a lot of IPv6 support; progress is slow but outside contributors
      have added a lot of functionality.
* Two big issues with BSD: filesystem hierarchy standard (FHS)
  * Every Unix has its own FHS standard.
  * BSD use of `/run` is actually written to the root filesystem (it's not
    ephemeral as cloud-init treats it).
    * Need to push distro-specific treatment of ephemeral filesystem.
* AIX has announced that they would like to join the cloud hype.
* The hope from Mina's work has paved enough of a path to [sic]

### Presentation: Status of cloud-init versions and support in various distribution downstreams

Presented by: Chad Smith (Canonical)

* Refresh our understanding of downstream support matrix lifetime.
* Review Ubuntu, Debian, openSUSE, FreeBSD, Alpine, Amazon Linux.
* Are distributions pushing updates into stable releases?
  * Ubuntu pulls the latest release to stable releases: 20.04, 22.04, 23.04
  * Canonical provides ESM (Expanded Security Maintenance).
  * cloud-init
* Frederick: Can cloud-init make a backwards compatibility for release?
  * Define with labels whether changesets are backward compatible or not
* Noah: cloud-init is not consistently clear whether interface changes or
  behavior changes, so downstream consumers can better assess risk profile.
  * [Concern]: Don't have a defined policy for determining whether we will
    pull the latest cloud-init releases into stable releases on Debian/Amazon
    Linux.
  * Frederick: Lack of a contract is what hinders us here, if we can be more
    strenuous for our [sic]
* James: Ubuntu tries to keep behavior consistent on stable releases, and has
  downstream debian/patches to hold stable behavior.
* ChrisP: Azure finds the update process valuable especially in relation to
  their datasource.
* Chad: This release process is a large burden on the project.
* John: New features on ESM Ubuntu versions? Divergence between cloud-init
  versions.
* Noah: Amazon Linux and Debian try to suggest to customers to migrate to newer
  releases, instead of trying to backport those features to stable releases
* NoahM: Would it make sense to generalize the SRU process more for other
  distros to better engage a broader group of contributors and drive quality?
* James: From the Ubuntu perspective we have a history of finding regressions
  after each SRU. This may impact partners if we require a vote on releases to
  ensure stable release updates are 'approved' for various downstreams.
* Noah: Try leaning toward pushing some of the SRU.
* John C: Have clouds/partners/distros publish/queue testing.
* Robert S: We could ask clouds to sponsor accounts for distribution testing
  * Want to drive ability to [sic]
* [ACTION] Releases: document and downstream patches we apply
* Noah M: do you have a separate policy for how you approach those downstream
  patches
* [ACTION] cloud-init PRs that break compatibility add a new 'breaking-change'
  label.
  * Alberto: Also in the commit message?
  * John C: Potential templates in commit messages indicating breaking change.
  * John C: [Example of convention](https://www.conventionalcommits.org/en/v1.0.0)
* Robert S: Need more conspicuous [breaking change] in release notes for the
  release.
  * Want this in the release changelog or in git commit messages as metadata
    -- it raises awareness.
* [Quotable]: "You have to deal with me if you want the stuff" -- Robert S
  * Robert S: Can we add a prefix in commit message metadata to differentiate
    "bug fix" from "feature".
  * [Outcome] Multiple people preferring changelog route
* SUSE patches are found here: https://build.opensuse.org/package/show/Cloud:Tools/cloud-init
  * Is https://repology.org/project/cloud-init/versions up to date?
* [ACTION] Community, Partners Clouds and Distro maintainers please update the
  support matrix by end of cloud-init summit with the latest details of what
  version of cloud-init is where, and whether that release receives updates.

| Distro/Release       | Cloud-init version | Receives cloud-init updates | End of Life      |
| -------------------- | ------------------ | --------------------------- | ---------------- |
| Ubuntu 16.04, 18.04  | 21.1-19, 23.1.2    | CVE / Security              | Depends on ESM   |
| Ubuntu 20.04, 22.04, 23.04 | latest       | yes                         | Not EOL          |
| SLE 12               | 20.2               | Only CVE fixes              | Oct 31st 2027    |
| SLE 15               | 23.1               | Yes                         | Jul 31st 2031    |
| openSUSE Leap        | 23.1               | Yes                         | Not EOL          |
| openSUSE Tumbleweed  | 23.1               | Yes                         | Never            |
| Oracle Linux 7       | 19.4               | CVE / Security              | Dec 24 + depends |
| Oracle Linux 8       | 22.1               |	                          | Jul 29 + depends |
| Oracle Linux 9       | 22.1               |	                          | Jul 32 + depends |
| RHEL 8               | 23.1               | CVE / Security              |                  |
| RHEL 9               | 23.1               | CVE / Security              |                  |

#### Release patch links

* [Ubuntu 20.04](https://github.com/canonical/cloud-init/tree/ubuntu/focal/debian/patches)
* [Ubuntu 22.04](https://github.com/canonical/cloud-init/tree/ubuntu/jammy/debian/patches)
* [Suse Patches](https://build.opensuse.org/package/show/Cloud:Tools/cloud-init)

### Roundtable: Python version support matrix and deprecation plan

Chaired by: James Falcon (Canonical)

* Record current Python versions under long term support by various
  distributions versions.
* Ubuntu: LTS support matrix.
* Policy for deprecation.
* What keeps you on an older version?
* SUSE freezes once the distro hits stable.
  * openSUSE 15 concluded that Python 3.11 and all dependencies [sic]
* Chris P: Why do you want to update to newer python version?
  * James: Newer features provided.
* John C: how to add new Python features and maintain ESM / LTS support?
* Fred L/Noah M: The cost of moving to newer Python versions is "beyond
  annoying" -- it would be helpful to take into account the costs of that
  shift to newer features as it forces downstream work.
* Noah M: If there are critical security fixes added to upstream, is it
  possible for ease of downstream adoption of security features?
* Robert S: How do we test this across multiple versions when we end up
  developing with our local Python version. This leads to gaps because we are
  human. Does this come down to testing to assert?
  * How can we integrate unit tests so that each flavor and/or distribution can
    be exercised everywhere to assert we don't have regressions?
* Robert S: I still pull in new major versions of cloud-init into supported
  versions (including 3.6).
  * "I have no fear", update twice a year.
  * It's not possible to test everywhere, OpenStack is one of those cases.
  * Customers are very helpful in that regard as they will prefer to test
    newer versions and collaborate with SUSE on verification.
* Robert S: Potential pivot to Python 3.11 in 9 months.
* Mina: 3 supported BSD releases (12.4, 13.2. 11.X) have been EOL for a few
  months now:
  * Next release is 14, coming out as soon as OpenSSL integration is completed
    and current LLVM release 16.
  * 3rd party software: all FreeBSD releases contain the same version of
    cloud-init. So latest cloud-init releases are published to all active
    supported releases.
  * Also, there is a quarterly release of those ports to provide "stable
    adopters" with only bug and security issues being fixed.
  * Bleeding edge version of cloud-init is available in the form of the
    `net/cloud-init-devel` port.
* Chris P: How many distros actually pull regular new upstream cloud-init
  versions which may need additional testing?
  * Noah: Debian don't currently regularly pull cloud-init into supported
    releases -- only backport when we need to.

| Distribution/Release | Python version | End of life | Takes upstream release |
| -------------------- | -------------- | ----------- | ---------------------- |
| Ubuntu/Bionic (18.04)| 3.6            | ~2030?      | Security only          |
| Ubuntu/Focal (20.04) | 3.8            | ~2025       | Yes                    |
| SUSE                 | 3.6            | ~9--12 months |                      |
| openSUSE 15          | 3.6 (soon 3.11)| Not EOL     | Yes                    |
| Mariner 2            | 3.9            | No EOL      | Yes                    |
| RHEL 8               | 3.6            | May 2024?   | Python 38 available but not default |
| Amazon Linux 2023    | 3.9            | ~2028       | Not systematically     |


### Roundtable: status of distribution downstream patches

Hosted by: Brett Holman (Canonical)

* [REQUEST] Looking for public download patches that partners are willing to
  review.
* Chris P: Azure Mariner team carries downstream patches.
* Amazon Linux has private patches that it may make sense to upstream -- it's a
  [ACTION].
* Cloud-init upstream wants to avoid breaking private downstream patches if/when we change internal APIs or function signatures.
* Robert S:
  * cloud-init documentation would be helpful to generate a list of what
    distributions.
  * James: We already generate distribution support in the rendered docs.
  * Noah: `cloud-config.tmpl` does also override and filter out certain modules

### Roundtable: status of testing and/or publication of cloud-init in various OSes

Hosted by: Chad Smith (Canonical)

* What gates publication of cloud-init on each distribution?
* Review Ubuntu, Debian, openSUSE, FreeBSD, Alpine, RedHat if possible.
* Noah M: May not be giving away that we are not running integration tests locally.
  * We rely on upstream testing behavior during releases for quality
  * Debian: Unittests run as part of the package build process.
  * Existing upstream integration tests not run in Debian or Amazon Linux right
    now.
  * Amazon Linux has similar integration-type tests -- realistically,
    can/should be converted to [sic]
  * Different framework for testing packages in the distribution in general:
    * Possible refactor of Amazon Linux could be reasonable for [sic]
    * May be worthwhile to investigate running integration tests with Debian
      and Amazon Linux.
* Chad: Better documentation would take it a long way.
* Chris P: We rely on cloud-int upstream testing to get the breadth of testing
  for broad features.
  * Test with cloud-init upgraded in images at scale, to check for regressions.
  * Looking for checkbox for release.
  * Noah M: are you testing cloud-init features specifically or using existing
    test infra to see if you have regressions related to [sic]
* Chad: So we have people leverage existing testing as well as people testing
  things more pertinent to them.
* Guillerme: Oracle have general infrastructure tests that watch for
  regressions with new cloud-init images.
* Chad: We want to make it easy to let others run integration tests while also
  getting that feedback from other platforms. Are there any public endpoints
  that upstream can consume?
* Dermot: What about cloud providers provide a "stock metadata" that allows
  providers to provide emulated content to mock the IMDS?
  * Robert: Once we mock IMDS, there are other platform services.

### Demo: Integration testing updates for pycloudlib

Presented by: James Falcon (Canonical)

* [Slides: Integration testing updates](https://docs.google.com/presentation/d/1e5p9FW9EI9FxnEyLPhpIA79GVGdyQ2aIVyX8Ggb29L8/)
* Generalized for all clouds.
* Noah M: How do you get the new version of cloud-init on the image under test?
  * James: We start from a public image ->
    * Launch image ->
    * Upgrade cloud-init ->
    * Run `cloud-init clean --logs`
* Pycloudlib:
  * Most Linux distributions are supported given the ability to discover.
* James:
  * Per-PR testing CI runs on Ubuntu on LXD.
  * Why would CI [sic]
  * Jenkins daily runners give a healthy signal on GCE, EC2, Azure.
  * For Rust project: they talked directly to GitHub about increasing governor.
  * Chris P: Is there a mechanism to validate certain PRs on Azure?
  * In Rust: Bohrs-bot in GitHub to kick off conditional jobs:
    * https://forge.rust-lang.org/infra/docs/bors.html
    * Fork of https://github.com/rust-lang/homu
* Chris P: Is Jenkins publicly accessible?
  * Chad: Nope -- security issue, due to malicious plugins.
  * Chris: We would like to trigger specific test runs on Azure.
* Ahn: Do you use merge-queue? To queue CI run after Merging?
* Mina: How has the move from BZR -> GH changed your workflow?
  * It feels like there is a stumbling block in how pull requests are being
    designed given that some workflows are not ideal for some teams.
* James: I don't think it's realistic for cloud-init upstream to test all
  distros in our Jenkins test runner.
  * Chris P: What is the blocker to that: cost?
  * John C: Some testing accounts are tied to costs and accounts that are
    sponsored.
  * Chris P: If we can sort cloud accounts/costs, would that provide us with
    testing?
  * John C: Looking at our matrix, we have to understand the depth we want in
    the support matrix -- of how many instance types/sizes.
  * Discussions with cloud platforms are needed to determine what instance
    type/distro matrix is "good enough".
  * Robert S: This matrix only continues to grow and is not sustainable for all
    clouds and all distros. It's a combinatorial problem.
  * We want the ability to specialize tests to a given cloud based on where the
    changes are scoped (per datasource/per distro) to reduce test matrix costs
    and make testing sustainable.
* Chris P: If you see upstream tests, does that give you a sense of certainty
  that allows you to avoid certain tests?
  * Robert S: I just take it and accept the work being done upstream and say
    "thank you".
* Robert S: pycloudlib has a dependency problem that makes it hard because it
  pulls in all Botocore Azure SDK etc. to support all platforms.
  * For some projects in SUSE they have conditional build flags that
    limit/segment the dependencies to make it easier to only depend on certain
    SDKs.
* Chad: It's possible to add more segmentation in our tests, but would be
  valuable.
* Waldi: Debian uses Apache Libcloud.
* Frederick L: There are a number of moving pieces trying to track with the
  test matrix. Clouds should be best placed to define proper testing.
  * Clouds should do more of the testing as they are best placed to do that
    testing.
* John C: Sounds like it talks around a web service that would allow for
  posting test results.
  * Mina: Can we establish a way to trigger specific builds on Azure on a
    per-PR basis?
* Robert S: We have OpenQA, but there's still the issue of cost.
  * If upstream works on documentation for integration testing per
    distribution, downstreams can consume that and try to leverage those docs
    to make per-distro test runs.
    * If we have a 30-step procedure for how best to integration test.
    * Might want to solve a small problem to define manual steps to enable
      downstreams to better integration test, allow developers to enable
      integration-tests on their distro/cloud rather than trying to define
      bigger funding/policies and public services.
    * If it's relatively easy for SUSE to kickoff and run tests, but we'd want more documentation on the procedure for setup and integration test runs
* Takeaways:
  * [ACTION] Better docs for integration-tests to onboard other distros/clouds for
    testing.
  * [ACTION] Improve visibility to upstream test status.
  * [ACTION] Microsoft or other clouds engaged in integration-testing should
    determine (per-cloud/distro) what makes sense for leveraging where partners
    are investing their development time.
  * Entire test matrix is likely too large for any single entity to test
    everything.
* Robert S: "This is an fdisk problem; this is not my problem".

### Presentation: Security policy overview

Presented by: Chad Smith (Canonical)

* For upstream GitHub pull requests that warrant a security review, add the
  label "security".
* [Overview for filing new security issues](https://github.com/canonical/cloud-init/security/policy)
* Either:
  1. Send an email to `cloud-init-security@lists.canonical.com` reporting the
     security bug, or
  1. [File a bug](https://bugs.launchpad.net/ubuntu/+source/cloud-init/+filebug)
     and mark it as "Private Security".
* After the bug is received, the issue is triaged within 2 working days of
  being reported and a response is sent to the reporter.
* The `cloud-init-security@lists.canonical.com` is private.
* Any vulnerability disclosed to the mailing list or filing a private security
  bug should be treated as embargoed, since any affected parties will
  coordinate a reasonable disclosure release date:
  * Disclosure date is based on bug severity, affected party development time
    for the release and fix publication
* If a CVE is warranted, the Canonical security team will reserve a CVE ID that
  will be represented on the bug and the published bug fix.
* At the disclosure date, an email is sent to `cloud-init@lists.launchpad.net`.
* Review new or dropped contacts needed for security notifications?
  [REDACTED emails]

### Demo: Ubuntu live installer

Presented by: Dan Bungert (Canonical)

* [Slides: Subiquity, Autoinstall, and Cloud-init](https://docs.google.com/presentation/d/1Qd3soaBnbz0f3zmtp1IXMotwAqsUW0Llvx5dTbCW_7g/edit#slide=id.g239da370174_0_22)

### Demo: Canonical CPC, test framework

Presented by: John Chittum (Canonical public cloud manager)

* [Slides: Ubuntu Build And Test CloudInit](https://drive.google.com/file/d/1gwrHqpXB9gpY_ddx38jxRY81QDKAV0uu/view?usp=sharing)


### Demo: Cloud-init schema validation and validation service

Presented by: Alberto Contreras (Canonical)

* [Slides: cloud-init schemas](https://docs.google.com/presentation/d/1Pn2I3dWw4rzbZWxuuU9mTrtbhlJonq3NsX0DLAztkK4)
* Minimal: Some distros have different schemas, how to deal with that?
* Chad: Separate schema files?
* Robert S: This is going to be an "after the fact thing". Users are not going
  to use it.
* [ACTION] Print schema warnings / errors to the console / journald: More
  visibility.
* Chris P, Robert S, AWS: Hard-error on schema errors is very valuable.
* [ACTION]: Do not show subsequent error traces in the case of a non-valid
  cloud-config.
* Noah M: I want hard errors at console for schema validation problems.
  * Dermot: Some cloud providers don't give console support by default, so
    expecting the "error" output console being your primary means of
    communication will not help certain platforms.
  * Chris P: Customize strict failures depending on use-case and clouds.
    * [ACTION] Investigate providing an option to make schema errors a hard
       error at system boot that is configurable by cloud/distro image
       creation. Imagine `error_handling` config keys.

## Day 2 running notes, per session

### Presentation: cloud-init and Alpine Linux

Presented by: Dermot Bradley (Alpine Linux)
* [Slides: cloud-init and alpine](https://drive.google.com/file/d/1S1p5d-8aC36H2WPJuE84OK1ynZWv4cfj/view?usp=drive_link)
* 3 years package maintainer for cloud-init and cloud-utils.
* Musl vs. glibc (developer focus is POSIX-compliance, reluctance to
  non-POSIX compliance) any strong non-POSIX features devs rely on make this a
  blocker to Alpine devs due to Musl dependency.
* Non systemd, busybox's init and [sic]
* Alpine doesn't "not like" systemd, but systemd developers don't support
  alternatives to glibc so it makes systemd support tough.
* Alpine not udev, they use mdev. Initframfs uses mdev, so udev support, while
  packaged, may cause config friction with other parses of the busybox init
  stack.
* `sudo` is packaged but not used in favor of `doas` due to some of the fairly
  frequent security concerns with `sudo`.
* Nocould-net writes to ENI and seeing secondary writes of ENI config files
  that don't effectively ifdown the previous temporary interfaces.
* Renderer issues with multi-IPv4 addresses showing up in wrong net config
  section, likely problems with network config/internal conversion logic.
* Fix hook-hotplug to avoid hadcoding bash for the script.
* Fix lock_passwd: Openssh config: password: * behavior is difference in BSD
  vs. Linux; "special cased" due to PAM enabled.
  * If PAM is not enabled, * means locked.
  * Alpine has PAM/Kerberos/other:
    * Alpine has to build images with PAM-enabled otherwise passwords [sic]
* Problems:
  * Alpine has to grab latest Python for edge repo.
  * Edge repo moves to latest Python 1-2 days for new Python version.
  * Could create a window where cloud-init could be broken.
* Future work:
  * Alternatives to SSH: dropbear and tinySSH.
  * `cc_wireguard` for Alpine, non-Ubuntu.
  * Improve console output layout to make it 80 chars wide given IPv6
    output/routes, line-wrap etc.
* [Tooling Dermot uses for creating images](https://github.com/dermotbradley/create-alpine-disk-image)
* Questions:
  * Is it worth calling out specific distribution concerns/dependencies in
    cloud-init docs (mdev/busybox/non-bash/doas concerns)?
    * Noah M: do you need to make it granular per distro: POSIX/non-POSIX
      approaches?
    * Dermot: May not need much in the way of docs.
      * For systemd/non-systemd environments, Alpine isn't alone, Gentoo is in
        that, Gentoo directory provides cloud-init code drop-ins.
      * Checked in IRC channel to get an impression from the project, didn't
        get a handle on the project stance. Opinion is that maybe Alpine is the
        only distro using `init.d`.
    * Brett H: There was an effort recently -- [Devuan](https://www.devuan.org/)
      attempted to add cloud-init and they didn't try to upstream it, COS
      (Google) may be using OpenRC, carry sid?
  * How do you, as Alpine maintainer, track new issues/features/development or
    what needs/ongoing work?
    * Prioritization is up to Dermot as maintainer.
    * Alpine has official cloud-init images for AWS.
    * [Tinycloud](https://gitlab.alpinelinux.org/alpine/cloud/tiny-cloud) that core Alpine developers use.
    * [ACTION - done] Dermot to provide links to "official images" in clouds or public
      repository/website/service: [Alpine Linux website and downloads](https://alpinelinux.org/cloud/)
    * Cost prohibitive to host "official" images in multiple clouds etc.
      * Some talk about making official images on GCP and other clouds.
      * One person paying for all clouds.
      * Noah M: talk to Debian publishing from, AWS account is sponsored by
        AWS... there are similar accounts.
        * [ACTION] Noah M can help Dermot get in touch with right people for
          open source engagement to start talks about open source sponsor
          accounts for hosting "official images".

### Presentation: Documentation overhaul and policy for cloud-init

Presented by: Sally Makin (Canonical)

* [Slides](https://docs.google.com/presentation/d/1aULy2jy6yil-wncMLLcHYWsDbFwRjS9aVOvxH-UQk08/edit?usp=sharing)
* Mina: I've seen some people complain that the style is a bit hard to read...
  that the fonts are too thin and light -- maybe try Atkinson Hyperlegible.
* Kyler just opened an issue on the docs for how arrow navigation works (module
  page, not working as expected).
* Robert S: https://cloud-init.readthedocs.io is distro agnostic, people
  discovering docs may get the opposite impression with Canonical/Ubuntu in the
  URL -- others may be concerned:
  * What do other distro downstreams do? Reflect docs?
  * Sally: https://readthedocs.com requires using the company name in the slug
    as it's pulled from the repo. I asked RTD support if we could get rid of
    that, they said absolutely not.
* Mina suggests https://cloud-init.io (+1 from Noah):
  * [ACTION] Access may be an issue, Sally will investigate

### Roundtable: boot speed in cloud-init

Chaired by: Chad, Alberto, Catherine Redfield (Canonical)

* [Slides for discussion points](https://docs.google.com/presentation/d/1OunV5fXFBkxg61y4wzApNmpEbmqIUlLpA9DQ92g7D0Y/edit#slide=id.g25f04f72223_2_0)
* Robert S: Ran time to SSH tests on SUSE years ago. GCE: 38.5s EC2: 52.2s
  Azure: 104s. After time to SSH, rest of come up is reasonably consistent.
  Does time cloud-init takes make a big difference?
* Noah: These numbers have come way down. Cloud-init is now a bigger part of
  it. EC2 has made Amazon Linux changes: IO is a really significant contributor
  when IO is cold. Reducing data loaded from disk helps a lot. E.g., reduce
  size of initrd. All modules and dependencies being loaded contributes a lot.
* Mina: Firecracker is the biggest one contributing to FreeBSD.
  * MicroVM hypervisor: AWS open source project, EC2-specific hypervisor
  * Optimizing BSD for Firecracker leads to approaches that could be applicable
    to generic hypervisors (Colin Percival) ec2-boot-bench for getting
    fine-grained launch time instruments (time to network response, port 22
    open etc).
* Chad: Agreement that time to SSH/network availability on first boot is the
  priority.
* Andrew J: Time to SSH may not be what all users actually care about, but it's
  what Gartner and others measure when they compare clouds, so it matters
  anyway, and it's not a bad proxy measurement.
* EC2 -- vast majority of instances don't reboot, they are torn down after
  they're no longer used, upgrade to new instances.
* John C: "time to workload" suggestion from some clouds, but "what workload"
  is the important question... hard to define besides just treating SSH.
* Dermot: Typically running chrony (waits til time sync) impact boot time,
  individual [sic]
* Mina: Some large cloud-init scenarios include reboot to ensure everything
  comes up.
* John: In Kubernetes, time to serve container is most important.
* Noah: Early init might not be as small as you think. Especially BIOS boot.
  * 13 CPU instruction 508 bytes of disk at the same time lots of I/Os -- that
    significantly impacts cost to boot.
  * Less pronounced in UEFI.
* Chad: Compression has a large effect on initrd time. Tradeoff between image
  size and speed. Also, complexity of storage and networking stack. Can be 2+
  minutes for very complex instance types (back to slides so not taking notes
  on that).
* Dermot: Does GRUB currently make use of any seed passed by UEFI? That would
  speed up initial entropy seeding. Re: stage 3 improvements.
* Noah: Time spent generating SSH host keys.
* Noah: Can we reduce IMDS keys and limit the initial crawl footprint for
  init-local?
  * Can we ask for a single JSON representation of critical config data.
    * Guillaume: We might not get a warm initial response but if it's never
      asked for it will never be put into any roadmap either.
  * CatRed: To answer your initial question, we know what minimal keys we need,
    * To ask for individual keys, it may make sense to look at a single URL to
      obtain that data.
    * Could we ask for "cloud-init-local" URL from IMDS to seed content?
  * Noah M: Early boot keys is not necessarily cloud-init-specific so it may be
    easier to define a generalized "early boot config" that isn't
    cloud-specific.
  * Noah M: The CPU cost associated with multiple requests amortized across all
    of EC2 is likely to be very high; the potential for savings is also high
    and therefore may be justified in order to improve boot time, improve
    performance, and reduce costs.
  * Also consider early boot keys in non-network locations (e.g., SMBIOS).
* Dermot: Also look at caching opening the JSON schema file.
* Chad/John: Avoid cost of ephemeral DHCP by keeping the IMDS data local to
  the instance rather than using network (also cuts down security concerns).
* Chad: Considering pre-compiled binary too, but that would be a big
  effort/cost.
* Noah: Rather than re-initializing everything, can we use a persistent
  process?
  * Investigated a signal/flag condition that'd avoid loading Python in later
    boot stages to avoid the Python initialization cost.
  * Noah has seen hundreds of milliseconds for Python spin-up.
  * Chad: Also an option to have a smaller cloud-init with reduced stages.
* Biggest question around removing host key types: are certain ones required
  for compliance? In Amazon we had to re-enable older types for FIPS.
* Chris: On some distros, SSH starts early and then needs to restart after SSH
  module. If the module moved earlier, we might be able to cut the restart.
* Robert: For use cases that need large scale, you'll probably have a minimal
  cloud-config, so we probably shouldn't worry about efficiencies in the later
  modules.
* Dan: We've had a few bugs around implicit ordering cycles.
* Chad: If we change/remove waiting for snap seeding, there's no indication
  that cloud-init is actually waiting for snap seeding.
* Minimal cloud-init in a precompiled language.
  * Nells: Would definitely be interested in collaborating should Rust be
    pursued.
* [ACTION] John: Get from clouds/partners: what is the minimal system/features
  that partners care about.
  * User creation, SSH key setup, what kind of network config is needed.
  * E.g., smart NICs, appliances, or immutable apps/solutions.
* Robert: Images with cloud-init vs. images with Ignition + Afterburn. On the
  spot numbers for consideration:
  * Data collected on EC2 on t2.micro in us-east-1.
  * Instance of SLE-Micro which uses Ignition/Afterburn.
    * Startup finished in 2.860s (kernel) + 12.437s (initrd).
  * SLES 15 SP5 basically the same initrd (no Ignition/Afterburn).
    * Startup finished in 2.716s (kernel) + 5.160s (initrd).
    * Cloud-init in this instance (all services per `systemd-analyze`) 11.143s.
      * Off this 9.248s cloud-init-local.service.
* Log levels:
   * []: Noted that they do find the logs saying how many bytes are read --
     logs helpful for debugging.

### Demo: instance-id in LXD

Presented by: James

* Followed by roundtable
* [Roundtable slides: instance-id](https://docs.google.com/presentation/d/1VYYKUErQcMiYLFN0Slisz-bYT8f_iskiu-bkyWrZp70/edit#slide=id.g2595c67feb8_0_0)
* Can we determine a consistent set of rules for when we get a new instance-id
  from clouds and what it means to cloud-init for those cases?
* Noah M: If a host is rebooted and IMDS is unavailable, cloud-init (upon
  seeing new instance ID) triggers the "re-run" behavior which is undesirable.
  * If we have a way to see instance-id out of something like SMBIOS, it would
    prevent unnecessarily triggering re-run from cloud-init.
* Chad: This is happening because datasource moved from "DataSourceEC2" to
  "DataSourceNone". We can likely improve this behavior as instances usually
  aren't being moved between clouds.
* Some clouds use regen network per boot:
  * Amazon Linux regenerates network every boot and doesn't use cloud-init for
    that.
  * Frederick: Some customers felt they wanted to block IMDS access after first
    boot for their use case.
* Mina: Any goal to make modules more idempotent?
  * Chad: A good ideal and something that we can document as policy/intent for
    both module creation as well as ongoing module review.
  * [ACTION] follow-up to define policy or approach for better ensuring and
    reviewing idempotent `PER_INSTANCE` defined `cc_*` module runs in light of
    reruns will be idempotent.
* Is it useful to have a separate mechanism to define a scoped IS change to
  limit scope of the config changes cloud-init takes (network vs. everything
  vs. an individual config modules)?

### Demo: cloud testing tools in cloud-init ecosystem

Presented by: Chris Patterson and Ahn Vo (Microsoft)

* We all build our own tools/testing/performance/reliability.
* Are there tools out there for perf and reliability that could be leveraged?
  * We may all have downstream/specific tools to scrape cloud-init logs looking
    at `cloud-init.logs` to scape WARNINGS/ERRORS from logs to determine [sic]
* Azure spends a lot of time to detect errors as discovered in-house, to define
  dhclient failed to bring up networking in PPS stage.
* If there were a repo where partners can provide their `regex` for log
  analysis, to determine failures and watch for regressions.
* LISA tools do their own thing, we do our own thing.
* Anh: cloud-init collect logs; can we supplement or reduce the files that are
  being collected, maybe with a manifest?
  * Chad: sounds like a good feature request.
  * [ACTION] file a bug for this feature for extending default behavior.
* Chris P: Are there scripts/checkpoints for regressions?
  * Robert S: When I do cloud-init update to latest release I create new images
    and launch on cloud X,Y,Z uses [sic]
* Chris P: are there plans to surface `cloud-init status --format=json`?
  * Brett H: work in progress on warnings raised through cloud-init status
  * There is a desire from Azure to also reflect schema warnings as more visible    in console logs

### Roundtable: Rotten tomatoes: what can the cloud-init project do better?

Brainstorming session on areas for improvement, policy changes, automation,
feature sets, and communication changes that may help improve cloud-init as a
project / engagement from communities. Open season for suggestions, gripes,
improvements to be had!

**How should we engage the community more? What blocks you?**

* Former IRC meetings are no longer held, having synchronous meetings wasn't
  supportable and significantly useful for broad timezone support.
  * Mina: That status meeting was always at a terrible time... for people with
    small children in Europe, anyway.

**Preferred communication?**
* Noah: Mailing list
  * Robert: Mail is good. Meetings were nice but too busy and not great time to
    attend. Weekly summary would be nice.
  * Noah: More than just `git log`, but a top level summary would be best.
  * Maybe weekly link list of landed PRs, GH account name.
  * [ACTION] Work with NellS (Microsoft) to better define weekly digests from
    GitHub and reporting (to cloud-init mailing list) the landed PRs and
    authors, maybe supplemental context.
* Robert: It'd be good to better highlight the problems/actions taken for a
  CVE, especially when historical data is involved.
  * [ACTION] review security policy for data we release to our security
    partners. If we know we are dealing with distro-specific and packaging
    concerns, it's best to provide that to partners during embargo time to
    allow them to prepare.
* Noah M: Small request -- really dislike "squash merge" on all pull requests.
  * It discards what I've done and the way I've architected the cohesive
    changes and understanding the intent. Prevents my ability in the future to
    understand the thought process for my changeset to bisect problems when
    they show up.
* Mina: That sounds like what I was talking about yesterday with respect to the
  PR workflow... https://jg.gg/2018/09/29/stacked-diffs-versus-pull-requests/
  * Stacked Diffs Versus Pull Requests | Jackson Gabbard's Blog
  * A post from Jackson Gabbard on Jackson Gabbard&#039;s Blog provided by:
    https://jg.gg
  * Mina: "I'll just open more pull requests" -- that's really difficult to do
    though, if they build on each other.
* [ACTION] Define policy or option for opting out of squash merges and what
  expectations there are around pull requests that want to avoid squash merges,
  and put it to the mailing list:
  * Mina: If opting out of squash merges, we probably want CI to pass on each
    commit.
  * Noah M: Part of the value of preserving individual commits is that you can
    use `git bisect` to check those commits individually and assert which
    commit broke.
    * Your individual commits shouldn't break the code so you need to
      understand what went wrong.

**Strong opinions around the mailing list vs. Discourse (forums)**

* John C: The nice thing about Discourse is that you can set up digests that
  act like mailing lists, Discourse provides the opportunity to dive deeper if
  necessary.
* James: Appreciate the ability to subscribe to individual threads.
* Noah + Robert: Prefer email.
* Robert S: Document list of config modules per distro.

### Roundtable: ISC-dhclient deprecation status

Chaired by: Brett Holman (Canonical)

* Review of changes that have happened in cloud-init for DHCP support.
* Questions/comments?
  * Robert S: SUSE has an interest in getting rid of the dhcpclient, file a
    request to make NetworkManager's dhclient callable from the command line.
* [INVESTIGATION] Dermot: Is IPv6 support considered in this
  migration/deprecation??
* Noah M: EC2 Amazon Linux: Talked about using a link local IPv4 address
  statically, or randomly choosing the address to avoid round trips with DHCP
  server, which is unnecessary.
  * EC2 doesn't use IPv6 LL but rather Unique Local address.
  * VPC == funny network, not proper layer2 network, don't have to worry about
    address conflicts
  * Brett H: Can be used as performance optimization but not cloud generic.
    * Walkthrough of PRs to support this feature set over the last year.
* Robert S: Maybe we rip all it out and farm it out to the kernel, Oracle
  requires network address in initrd.
* John C: initrd for Ubuntu is only a fallback mechanism if kernel itself does
  not boot -- straight kernel == no initrd.
* Chris P: In most cases we are doing DHCP on boot, why not have that DHCP
  config already in the image?
  * For iSCSI solutions, initrd has to have network up to get hold of the
    storage, so leverage it where necessary.
  * And NetworkManager has a DHCP engine that is not exposed on the command
    line -- might be able to get solutions that provide this.
* Amazon Linux: uses systemd-networkd.

### Wrap-up / Thanks

* Takeaways / roundtable / group retrospective on how the summit was organized.
* Physical summit location query
  * Seattle most likely candidate for next summit.
  * If European physical summit, may not have as much attendance from west
    coast clouds.
  * Merging cloud-init with UDS location as a separate conference?
  * What could be better handled next summit:
    * Communication?
    * Planning of firm talk start/stop talk times Y/N?
    * Types of talks, discussions, demos?
    * Timing of talks/timezone?
    * How to increase participation?
    * How was remote accessibility?
    * Should we open this up this event more broadly to the general community
      for drop-ins via public mailing list post/IRC post of talk times?
    * [YOUR_SUGGESTION_HERE]
* Would virtual conference get engagement?
* Project improvements
  * Communication channels?
  * Security publications?
  * Release frequencies: ~time based quarterly
  * Release hotfixes: patch release versioning on a 23.2.X pushed to GitHub,
    email sent out with the update.
  * [YOUR_IDEA_HERE]
  * Action items, investigations and follow-ups.
  * Continue to drive toward multi-distro/cloud integration-test adoption:
    * Add more official docs around integration test procedure for a new
      platform/distro.

Potential breakout development sessions from earlier discussions:
* Nells: Bring RUST GitHub workflows and policy to cloud-init.
* Better enabling integration-test use in non-Ubuntu environments.
  * Walk through procedure to get other distributions, drive live demo of
    integration testing, propose doc updates for extending integration tests on
    a new distribution.
* Strawman proposal for Schema warnings treated as hard errors (want
  configurable setting in images for certain platforms bool T/F, default False).
* Branch schema warnings emitted to console, not just logs.
* [ACTION] Review and discuss policy changes [around commits](https://www.conventionalcommits.org/en/v1.0.0).

Notes:
* Amazon Linux: every 2 years for release, would be more likely to snapshot
  cloud-init upstream released.
  * Some custom config modules for SELinux startup and other modules that may
    make sense to drive some of those changes.
* AL2023: version repositories.
  * When launching 2023 it's pinned to a specific version of the repository.
* AL1, AL2 and 2023 are different products:
  * Realistically have only shipped 3 versions of cloud-init.
