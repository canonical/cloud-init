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

## Checklist
<!-- Go over all the following points, and put an `x` in all the boxes
that apply. -->
- [ ] My code follows the process laid out in [the documentation](https://cloudinit.readthedocs.io/en/latest/development/index.html)
- [ ] I have updated or added any [unit tests](https://cloudinit.readthedocs.io/en/latest/development/testing.html) accordingly
- [ ] I have updated or added any [documentation](https://cloudinit.readthedocs.io/en/latest/development/contribute_docs.html) accordingly

## Merge type

- [x] Squash merge using "Proposed Commit Message"
- [ ] Rebase and merge unique commits. Requires commit messages per-commit each referencing the pull request number (#<PR_NUM>)
