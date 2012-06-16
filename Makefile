CWD=$(shell pwd)
PY_FILES=$(shell find cloudinit bin -name "*.py")

all: test

pylint:
	$(CWD)/tools/run-pylint $(PY_FILES)

pyflakes:
	pyflakes $(PY_FILES)

test:
	nosetests tests/unittests/

.PHONY: test pylint pyflakes

