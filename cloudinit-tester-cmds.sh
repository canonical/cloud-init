#!/usr/bin/env sh

# Use this script to run 3 useful invocations of cloudinit-tester-run.sh
# It's easier to imagine a fancier script that asks Y/n before each test,
# etc etc, but at that point it might make sense to switch to python

# Flake8
printf 'Running flake8 ...'
./cloudinit-tester-run.sh flake8 --verbose cloudinit tests/unittests
read -p 'flake8 done (press any key to continue ...)'

# pylint
printf 'Running pylint (this could take a while) ...'
./cloudinit-tester-run.sh pylint cloudinit tests/unittests
read -p '(press any key to continue ...)'

# pytest
printf 'Running pytest ...'
./cloudinit-tester-run.sh pytest tests/unittests
read -p '(press any key to continue ...)'