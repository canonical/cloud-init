CWD=$(shell pwd)
PYVER ?= $(shell for p in python3 python2; do \
	out=$$(command -v $$p 2>&1) && echo $$p && exit; done; exit 1)

noseopts ?= -v

YAML_FILES=$(shell find cloudinit tests tools -name "*.yaml" -type f )
YAML_FILES+=$(shell find doc/examples -name "cloud-config*.txt" -type f )

PIP_INSTALL := pip install

ifeq ($(PYVER),python3)
  pyflakes = pyflakes3
  unittests = unittest3
  yaml = yaml
else
ifeq ($(PYVER),python2)
  pyflakes = pyflakes
  unittests = unittest
else
  pyflakes = pyflakes pyflakes3
  unittests = unittest unittest3
endif
endif

ifeq ($(distro),)
  distro = redhat
endif

READ_VERSION=$(shell $(PYVER) $(CWD)/tools/read-version || \
  echo read-version-failed)
CODE_VERSION=$(shell $(PYVER) -c "from cloudinit import version; print(version.version_string())")


all: check

check: check_version test $(yaml)

style-check: pep8 $(pyflakes)

pep8:
	@$(CWD)/tools/run-pep8

pyflakes:
	@$(CWD)/tools/run-pyflakes

pyflakes3:
	@$(CWD)/tools/run-pyflakes3

unittest: clean_pyc
	nosetests $(noseopts) tests/unittests cloudinit

unittest3: clean_pyc
	nosetests3 $(noseopts) tests/unittests cloudinit

ci-deps-ubuntu:
	@$(PYVER) $(CWD)/tools/read-dependencies --distro ubuntu --test-distro

ci-deps-centos:
	@$(PYVER) $(CWD)/tools/read-dependencies --distro centos --test-distro

pip-requirements:
	@echo "Installing cloud-init dependencies..."
	$(PIP_INSTALL) -r "$@.txt" -q

pip-test-requirements:
	@echo "Installing cloud-init test dependencies..."
	$(PIP_INSTALL) -r "$@.txt" -q

test: $(unittests)

check_version:
	@if [ "$(READ_VERSION)" != "$(CODE_VERSION)" ]; then \
	    echo "Error: read-version version '$(READ_VERSION)'" \
	    "not equal to code version '$(CODE_VERSION)'"; exit 2; \
	    else true; fi

config/cloud.cfg:
	$(PYVER) ./tools/render-cloudcfg config/cloud.cfg.tmpl config/cloud.cfg

clean_pyc:
	@find . -type f -name "*.pyc" -delete

clean: clean_pyc
	rm -rf /var/log/cloud-init.log /var/lib/cloud/

yaml:
	@$(PYVER) $(CWD)/tools/validate-yaml.py $(YAML_FILES)

rpm:
	$(PYVER) ./packages/brpm --distro=$(distro)

srpm:
	$(PYVER) ./packages/brpm --srpm --distro=$(distro)

deb:
	@which debuild || \
		{ echo "Missing devscripts dependency. Install with:"; \
		  echo sudo apt-get install devscripts; exit 1; }

	$(PYVER) ./packages/bddeb

deb-src:
	@which debuild || \
		{ echo "Missing devscripts dependency. Install with:"; \
		  echo sudo apt-get install devscripts; exit 1; }
	$(PYVER) ./packages/bddeb -S -d


.PHONY: test pyflakes pyflakes3 clean pep8 rpm srpm deb deb-src yaml
.PHONY: check_version pip-test-requirements pip-requirements clean_pyc
.PHONY: unittest unittest3 style-check
