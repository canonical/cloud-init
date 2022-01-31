CWD=$(shell pwd)

YAML_FILES=$(shell find cloudinit tests tools -name "*.yaml" -type f )
YAML_FILES+=$(shell find doc/examples -name "cloud-config*.txt" -type f )

PYTHON = python3
PIP_INSTALL := pip3 install

ifeq ($(distro),)
  distro = redhat
endif

READ_VERSION=$(shell $(PYTHON) $(CWD)/tools/read-version || echo read-version-failed)
CODE_VERSION=$(shell $(PYTHON) -c "from cloudinit import version; print(version.version_string())")


all: check

check: check_version test yaml

style-check: flake8

flake8:
	@$(CWD)/tools/run-flake8

unittest: clean_pyc
	python3 -m pytest -v tests/unittests cloudinit

ci-deps-ubuntu:
	@$(PYTHON) $(CWD)/tools/read-dependencies --distro ubuntu --test-distro

ci-deps-centos:
	@$(PYTHON) $(CWD)/tools/read-dependencies --distro centos --test-distro

pip-requirements:
	@echo "Installing cloud-init dependencies..."
	$(PIP_INSTALL) -r "$@.txt" -q

pip-test-requirements:
	@echo "Installing cloud-init test dependencies..."
	$(PIP_INSTALL) -r "$@.txt" -q

test: unittest

check_version:
	@if [ "$(READ_VERSION)" != "$(CODE_VERSION)" ]; then \
	    echo "Error: read-version version '$(READ_VERSION)'" \
	    "not equal to code version '$(CODE_VERSION)'"; exit 2; \
	    else true; fi

config/cloud.cfg:
	$(PYTHON) ./tools/render-cloudcfg config/cloud.cfg.tmpl config/cloud.cfg

clean_pyc:
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name __pycache__ -delete

clean: clean_pyc
	rm -rf doc/rtd_html .tox .coverage

yaml:
	@$(PYTHON) $(CWD)/tools/validate-yaml.py $(YAML_FILES)

rpm:
	$(PYTHON) ./packages/brpm --distro=$(distro)

srpm:
	$(PYTHON) ./packages/brpm --srpm --distro=$(distro)

deb:
	@which debuild || \
		{ echo "Missing devscripts dependency. Install with:"; \
		  echo sudo apt-get install devscripts; exit 1; }

	$(PYTHON) ./packages/bddeb

deb-src:
	@which debuild || \
		{ echo "Missing devscripts dependency. Install with:"; \
		  echo sudo apt-get install devscripts; exit 1; }
	$(PYTHON) ./packages/bddeb -S -d

doc:
	tox -e doc

# Spell check && filter false positives
_CHECK_SPELLING := find doc -type f -exec spellintian {} + | \
       grep -v -e 'doc/rtd/topics/cli.rst: modules modules' \
               -e 'doc/examples/cloud-config-mcollective.txt: WARNING WARNING' \
               -e 'doc/examples/cloud-config-power-state.txt: Bye Bye' \
               -e 'doc/examples/cloud-config.txt: Bye Bye'


# For CI we require a failing return code when spellintian finds spelling errors
check_spelling:
	@! $(_CHECK_SPELLING)

# Manipulate the output of spellintian into a valid "sed" command which is run
# to fix the error
#
# Example spellintian output:
#
# doc/examples/kernel-cmdline.txt: everthing -> everything
#
# The "fix_spelling" target manipulates the above output into the following command
# and runs that command.
#
# sed -i "s/everthing/everything/g" doc/examples/kernel-cmdline.txt
#
# awk notes:
#
# -F ': | -> ' means use the strings ": " or " -> " as field delimeters
# \046 is octal for double quote
# $$2 will contain the second field, ($ must be escaped because this is in a Makefile)
#
# Limitation: duplicate words with newline between them are not automatically fixed
fix_spelling:
	@$(_CHECK_SPELLING) | \
		sed 's/ (duplicate word)//g' | \
		awk -F ': | -> ' '{printf "sed -i \047s/%s/%s/g\047 %s\n", $$2, $$3, $$1}' | \
		sh

.PHONY: test flake8 clean rpm srpm deb deb-src yaml
.PHONY: check_version pip-test-requirements pip-requirements clean_pyc
.PHONY: unittest style-check doc fix_spelling check_spelling
