import os

from Cheetah.Template import Template

from cloudinit import util

TEMPLATE_DIR = '/etc/cloud/templates/'


def render_to_file(template, outfile, searchList):
    contents = Template(file=os.path.join(TEMPLATE_DIR, template),
                 searchList=[searchList]).respond()
    util.write_file(outfile, contents)


def render_string(template, searchList):
    return Template(template, searchList=[searchList]).respond()
