CWD=$(shell pwd)
VARIANT ?= ubuntu

PYTHON ?= python3

NUM_ITER ?= 100

distro ?= redhat

GENERATOR_F=./systemd/cloud-init-generator
DS_IDENTIFY=./tools/ds-identify


all: check

check: test

unittest: clean_pyc
	$(PYTHON) -m pytest -v tests/unittests cloudinit

render-template:
	$(PYTHON) ./tools/render-template --variant=$(VARIANT) $(FILE) $(subst .tmpl,,$(FILE))

ci-deps-ubuntu:
	@$(PYTHON) $(CWD)/tools/read-dependencies --distro ubuntu --test-distro

ci-deps-centos:
	@$(PYTHON) $(CWD)/tools/read-dependencies --distro centos --test-distro

test: unittest

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

.PHONY: all check test clean rpm srpm deb deb-src clean_pyc
.PHONY: unittest render-template
.PHONY: clean_pytest clean_packaging clean_release doc
