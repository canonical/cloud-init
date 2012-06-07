#!/bin/bash

set -u

function find_src {
  files=`find bin cloudinit -type f | grep "py\$"`
  echo $files
}

function run_pep8 {
  echo "Running pep8 ..."
  files=$(find_src)
  ignores="E202,E501"
  output_filename="pep8.log"
  opts="--ignore=$ignores --repeat"
  pep8 ${opts} ${files} 2>&1 > $output_filename
  if [ "$?" -ne "0" ]; then
    echo "Some badness was found!"
  fi
  echo "Check '$output_filename' for a full report."
}

function run_pylint {
  echo "Running pylint ..."
  opts="--rcfile=pylintrc --output-format=parseable"
  files=$(find_src)
  output_filename="pylint.log"
  pylint ${opts} ${files} 2>&1 > $output_filename
  if [ "$?" -eq "1" ]; then
    # pylint --long-help
    # * 0 if everything went fine
    # * 1 if a fatal message was issued
    # * 2 if an error message was issued
    # * 4 if a warning message was issued
    # * 8 if a refactor message was issued
    # * 16 if a convention message was issued
    # * 32 on usage error
    echo "A fatal pylint error occurred!"
  else
    if [ "$?" -eq "0" ]; then
      echo "Your code is perfect you code master!"
    else
      echo "You are not yet a code master."
      grep -i "Your code" $output_filename
    fi
  fi
  echo "Check '$output_filename' for a full report."
}


run_pep8
run_pylint

