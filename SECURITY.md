# Security policy

The following documents the upstream cloud-init security policy.

## Reporting

File a [Private Security Report](https://github.com/canonical/cloud-init/security/advisories/new) with a description of the issue, the steps you took to create the issue, affected versions, and, if known, mitigations for the issue.
See the [Ubuntu Security disclosure policy](https://ubuntu.com/security/disclosure-policy) for more information.

## Evaluation

If the reported bug is deemed a real security issue a CVE is assigned by
the Canonical Security Team as CVE Numbering Authority (CNA).

If it is deemed a regular, non-security issue, the reporter will be asked to
follow typical bug reporting procedures.

## Disclosure

Disclosure of security issues will be made with a public statement. Once the
determined time for disclosure has arrived the following will occur:

* A public bug is filed/made public with vulnerability details, CVE,
  mitigations and where to obtain the fix
* An announcement is made to [GitHub Discussions](https://github.com/canonical/cloud-init/discussions)

## Supported versions

Each [cloud-init scheduled upstream release](https://github.com/canonical/cloud-init/milestones) is provided as updates to the [latest Ubuntu interim release and the two most recent Ubuntu LTS releases](https://ubuntu.com/about/release-cycle) to ensure common behavior of cloud-init on all Ubuntu standard security maintenance releases.

CVEs of critical or high CVSS severity will be backported to the all Ubuntu LTS releases and the two most recent Ubuntu ESM releases supported under Ubuntu Pro.
