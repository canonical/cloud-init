CWD=$(shell pwd)
VARIANT ?= ubuntu

YAML_FILES=$(shell find cloudinit tests tools -name "*.yaml" -type f )
YAML_FILES+=$(shell find doc/examples -name "cloud-config*.txt" -type f )

PYTHON ?= python3

NUM_ITER ?= 100

distro ?= redhat

READ_VERSION=$(shell $(PYTHON) $(CWD)/tools/read-version || echo read-version-failed)
CODE_VERSION=$(shell $(PYTHON) -c "from cloudinit import version; print(version.version_string())")
GENERATOR_F=./systemd/cloud-init-generator
DS_IDENTIFY=./tools/ds-identify
BENCHMARK=./tools/benchmark.sh


all: check

check: check_version test yaml

style-check: lint

lint:
	@$(CWD)/tools/run-lint

unittest: clean_pyc
	$(PYTHON) -m pytest -v tests/unittests cloudinit

render-template:
	$(PYTHON) ./tools/render-template --variant=$(VARIANT) $(FILE) $(subst .tmpl,,$(FILE))

# from systemd-generator(7) regarding generators:
# "We do recommend C code however, since generators are executed
# synchronously and hence delay the entire boot if they are slow."
#
# Our generator is a shell script. Make it easy to measure the
# generator. This should be monitored for performance regressions
benchmark-generator: FILE=$(GENERATOR_F).tmpl
benchmark-generator: VARIANT="benchmark"
benchmark-generator: export ITER=$(NUM_ITER)
benchmark-generator: render-template
	$(BENCHMARK) $(GENERATOR_F)

benchmark-ds-identify: export ITER=$(NUM_ITER)
benchmark-ds-identify:
	$(BENCHMARK) $(DS_IDENTIFY)

ci-deps-ubuntu:
	@$(PYTHON) $(CWD)/tools/read-dependencies --distro ubuntu --test-distro

ci-deps-centos:
	@$(PYTHON) $(CWD)/tools/read-dependencies --distro centos --test-distro

test: unittest

check_version:
	@if [ "$(READ_VERSION)" != "$(CODE_VERSION)" ]; then \
		echo "Error: read-version version '$(READ_VERSION)'" \
			"not equal to code version '$(CODE_VERSION)'"; \
		exit 2; \
	else true; fi

config/cloud.cfg:
	$(PYTHON) ./tools/render-template --is-yaml config/cloud.cfg.tmpl config/cloud.cfg

clean_pyc:
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name __pycache__ -delete

clean_pytest:
	rm -rf .cache htmlcov

clean_packaging:
	rm -rf srpm cloud_init.egg-info/ \
		cloud-init-*.tar.gz \
		cloud-init-*.tar.gz.asc \
		cloud-init.dsc \
		cloud-init_*.build \
		cloud-init_*.buildinfo \
		cloud-init_*.changes \
		cloud-init_*.deb \
		cloud-init_*.dsc \
		cloud-init_*.orig.tar.gz \
		cloud-init_*.tar.xz \
		cloud-init_*.upload

clean_release:
	rm -rf new-upstream-changes.txt commit.msg

clean: clean_pyc clean_pytest clean_packaging clean_release
	rm -rf doc/rtd_html .tox .coverage tags $(GENERATOR_F)

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

fmt:
	tox -e do_format && tox -e check_format

fmt-tip:
	tox -e do_format_tip && tox -e check_format_tip

# Spell check && filter false positives
_CHECK_SPELLING := find doc -type f -exec spellintian {} + | \
       grep -v -e 'doc/rtd/topics/cli.rst: modules modules' \
               -e 'doc/examples/cloud-config-mcollective.txt: WARNING WARNING' \
               -e 'doc/examples/cloud-config-power-state.txt: Bye Bye' \
               -e 'doc/examples/cloud-config.txt: Bye Bye' \
               -e 'doc/rtd/topics/cli.rst: DOCS DOCS' \
               -e 'dependant'


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

.PHONY: all check test lint clean rpm srpm deb deb-src yaml
.PHONY: check_version clean_pyc
.PHONY: unittest style-check fix_spelling render-template benchmark-generator
.PHONY: clean_pytest clean_packaging check_spelling clean_release doc
