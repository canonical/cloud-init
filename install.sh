#!/bin/sh

#                    cd $(DEB_SRCDIR) && $(call cdbs_python_binary,python$(cdbs_python_compile_version)) $(DEB_PYTHON_SETUP_CMD) install --root=$(cdbs_python_destdir) $(DEB_PYTHON_INSTALL_ARGS_ALL)
#                    for ddir in $(cdbs_python_destdir)/usr/lib/python?.?/dist-packages; do \
#                      [ -d $$ddir ] || continue; \
#                      sdir=$$(dirname $$ddir)/site-packages; \
#                      mkdir -p $$sdir; \
#                      tar -c -f - -C $$ddir . | tar -x -f - -C $$sdir; \
#                      rm -rf $$ddir; \
#                    done

DEB_PYTHON_INSTALL_ARGS_ALL="--no-compile -O0 --install-layout=deb"

destdir=$(readlink -f ${1})
[ -z "${destdir}" ] && { echo "give destdir"; exit 1; }
cd $(dirname ${0})
./setup.py install --root=${destdir} ${DEB_PYTHON_INSTALL_ARGS_ALL}

mkdir -p ${destdir}/usr/lib/pyshared
for x in ${destdir}/usr/lib/python2.6/dist-packages/*; do
   [ -d "$x" ] || continue
   [ ! -d "${destdir}/usr/lib/pyshared/${x##*/}" ] ||
      rm -Rf "${destdir}/usr/lib/pyshared/${x##*/}"
   mv $x ${destdir}/usr/lib/pyshared
done
rm -Rf ${destdir}/usr/lib/python2.6

for x in "${destdir}/usr/bin/"*.py; do
   [ -f "${x}" ] && mv "${x}" "${x%.py}"
done
