# Bug Test Configs

## purpose
Configs that reproduce bugs filed against cloud-init. Having test configs for
cloud-init bugs ensures that the fixes do not break in the future, and makes it
easy to see how many systems and platforms are effected by a new bug.

## structure
Should have one test config for most bugs filed. The name of the test should
contain ``lp`` followed by the bug number. It may also be useful to add a
comment to each bug config with a summary copied from the bug report.

# vi: ts=4 expandtab
