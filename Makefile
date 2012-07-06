CWD=$(shell pwd)
PY_FILES=$(shell find cloudinit bin -name "*.py")
PY_FILES+="bin/cloud-init"

all: test

pep8:
	$(CWD)/tools/run-pep8 $(PY_FILES)

pylint:
	$(CWD)/tools/run-pylint $(PY_FILES)

pyflakes:
	pyflakes $(PY_FILES)

test:
	nosetests $(noseopts) tests/unittests/

2to3:
	2to3 $(PY_FILES)

clean:
	rm -rf /var/log/cloud-init.log \
		   /var/lib/cloud/

rpm:
	cd packages && ./brpm

deb:
	cd packages && ./bddeb

.PHONY: test pylint pyflakes 2to3 clean pep8 rpm deb

