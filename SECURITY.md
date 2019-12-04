# Security Policy

The following documents the upstream cloud-init security policy.

## Reporting

If a user finds a security issue, they are requested to file a [private
security bug on Launchpad](https://bugs.launchpad.net/cloud-init/+filebug).
To ensure the information stays private, change the "This bug contains
information that is:" from "Public" to "Private Security" when filing.

After the bug is received, the issue is triaged within 2 working days of
being reported and a response is sent to the reporter.

## cloud-init-security

The cloud-init-security Launchpad team is a private, invite-only team used to
discuss and coordinate security issues with the project.

Any issues disclosed to the cloud-init-security mailing list are considered
embargoed and should only be discussed with other members of the
cloud-init-security mailing list before the coordinated release date, unless
specific exception is granted by the administrators of the mailing list. This
includes disclosure of any details related to the vulnerability or the
presence of a vulnerability itself. Violation of this policy may result in
removal from the list for the company or individual involved.

## Evaluation

If the reported bug is deemed a real security issue a CVE is assigned by
the Canonical Security Team as CVE Numbering Authority (CNA).

If it is deemed a regular, non-security, issue, the reporter will be asked to
follow typical bug reporting procedures.

In addition to the disclosure timeline, the core Canonical cloud-init team
will enlist the expertise of the Ubuntu Security team for guidance on
industry-standard disclosure practices as necessary.

If an issue specifically involves another distro or cloud vendor, additional
individuals will be informed of the issue to help in evaluation.

## Disclosure

Disclosure of security issues will be made with a public statement. Once the
determined time for disclosure has arrived the following will occur:

* A public bug is filed/made public with vulnerability details, CVE,
  mitigations and where to obtain the fix
* An email is sent to the [public cloud-init mailing list](https://lists.launchpad.net/cloud-init/)

The disclosure timeframe is coordinated with the reporter and members of the
  cloud-init-security list. This depends on a number of factors:
  
* The reporter might have their own disclosure timeline (e.g. Google Project
  Zero and many others use a 90-days after initial report OR when a fix
  becomes public)
* It might take time to decide upon and develop an appropriate fix
* A distros might want extra time to backport any possible fixes before
  the fix becomes public
* A cloud may need additional time to prepare to help customers or impliment
  a fix
* The issue might be deemed low priority
* May wish to to align with an upcoming planned release
