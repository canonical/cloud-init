
all: test

pylint:
	pylint cloudinit

pyflakes:
	pyflakes .

test:
	nosetests tests/unittests/

.PHONY: test pylint pyflakes

