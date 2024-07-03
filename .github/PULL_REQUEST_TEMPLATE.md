<!--
Thank you for submitting a PR to cloud-init!

To ease the process of reviewing your PR, do make sure to complete the following checklist **before** submitting a pull request.

- [ ] I have signed the CLA: https://ubuntu.com/legal/contributors
- [ ] I have added my Github username to ``tools/.github-cla-signers``
- [ ] I have included a comprehensive commit message using the guide below
- [ ] I have added unit tests to cover the new behavior under ``tests/unittests/``
  - Test files should map to source files i.e. a source file ``cloudinit/example.py`` should be tested by ``tests/unittests/test_example.py``
  - Run unit tests with ``tox -e py3``
- [ ] I have kept the change small, avoiding unnecessary whitespace or non-functional changes.
- [ ] I have added a reference to issues that this PR relates to in the PR message (Refs GH-1234, Fixes GH-1234)
- [ ] I have updated the documentation with the changed behavior.
  - If the change doesn't change the user interface and is trivial, this step may be skipped.
  - Cloud-config documentation is generated from the jsonschema.
  - Generate docs with ``tox -e docs``.
-->


## Proposed Commit Message
<!-- Include a proposed commit message because PRs are squash merged
by default.

See https://www.conventionalcommits.org/en/v1.0.0/#specification
for our commit message convention.

If the change is related to a particular cloud or particular distro,
please include the "optional scope" in the summary line. E.g.,
feat(ec2): Add support for foo to the baz

Types used by this project:
feat, fix, docs, ci, test, refactor, chore
-->
```
<type>(optional scope): <summary>  # no more than 72 characters

A description of what the change being made is and why it is being
made if the summary line is insufficient.  This should be wrapped at
72 characters.

If you need to write multiple paragraphs, feel free.

Fixes GH-NNNNN (GitHub Issue number. Remove line if irrelevant)
LP: #NNNNNN (Launchpad bug number. Remove line if irrelevant)
```

## Additional Context
<!-- If relevant -->

## Test Steps
<!-- Please include any steps necessary to verify (and reproduce if
this is a bug fix) this change on a live deployed system,
including any necessary configuration files, user-data,
setup, and teardown. Scripts used may be attached directly to this PR. -->


## Merge type

- [x] Squash merge using "Proposed Commit Message"
- [ ] Rebase and merge unique commits. Requires commit messages per-commit each referencing the pull request number (#<PR_NUM>)
