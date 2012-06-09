import os

from Cheetah.Template import Template

from cloudinit import settings
from cloudinit import util


def render_to_file(template, outfile, searchList):
    fn = template
    (base, ext) = os.path.splitext(fn)
    if ext != ".tmpl":
        fn = "%s.tmpl" % (fn)
    fn = os.path.join(settings.TEMPLATE_DIR, fn)
    contents = Template(file=fn, searchList=[searchList]).respond()
    util.write_file(outfile, contents)


def render_string(template, searchList):
    return Template(template, searchList=[searchList]).respond()
