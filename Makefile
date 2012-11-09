CWD=$(shell pwd)
PY_FILES=$(shell find cloudinit bin tests tools -name "*.py" -type f )
PY_FILES+="bin/cloud-init"

YAML_FILES=$(shell find cloudinit bin tests tools -name "*.yaml" -type f )
YAML_FILES+=$(shell find doc/examples -name "cloud-config*.txt" -type f )


all: test

pep8:
	@$(CWD)/tools/run-pep8 $(PY_FILES)

pylint:
	@$(CWD)/tools/run-pylint $(PY_FILES)

pyflakes:
	pyflakes $(PY_FILES)

test:
	@nosetests $(noseopts) tests/

2to3:
	2to3 $(PY_FILES)

clean:
	rm -rf /var/log/cloud-init.log \
		   /var/lib/cloud/

yaml:
	@$(CWD)/tools/validate-yaml.py $(YAML_FILES)
		   
rpm:
	./packages/brpm

deb:
	./packages/bddeb

.PHONY: test pylint pyflakes 2to3 clean pep8 rpm deb yaml

