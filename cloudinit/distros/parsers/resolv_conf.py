# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from six import StringIO

from cloudinit import util

from cloudinit.distros.parsers import chop_comment


# See: man resolv.conf
class ResolvConf(object):
    def __init__(self, text):
        self._text = text
        self._contents = None

    def parse(self):
        if self._contents is None:
            self._contents = self._parse(self._text)

    @property
    def nameservers(self):
        self.parse()
        return self._retr_option('nameserver')

    @property
    def local_domain(self):
        self.parse()
        dm = self._retr_option('domain')
        if dm:
            return dm[0]
        return None

    @property
    def search_domains(self):
        self.parse()
        current_sds = self._retr_option('search')
        flat_sds = []
        for sdlist in current_sds:
            for sd in sdlist.split(None):
                if sd:
                    flat_sds.append(sd)
        return flat_sds

    def __str__(self):
        self.parse()
        contents = StringIO()
        for (line_type, components) in self._contents:
            if line_type == 'blank':
                contents.write("\n")
            elif line_type == 'all_comment':
                contents.write("%s\n" % (components[0]))
            elif line_type == 'option':
                (cfg_opt, cfg_value, comment_tail) = components
                line = "%s %s" % (cfg_opt, cfg_value)
                if len(comment_tail):
                    line += comment_tail
                contents.write("%s\n" % (line))
        return contents.getvalue()

    def _retr_option(self, opt_name):
        found = []
        for (line_type, components) in self._contents:
            if line_type == 'option':
                (cfg_opt, cfg_value, _comment_tail) = components
                if cfg_opt == opt_name:
                    found.append(cfg_value)
        return found

    def add_nameserver(self, ns):
        self.parse()
        current_ns = self._retr_option('nameserver')
        new_ns = list(current_ns)
        new_ns.append(str(ns))
        new_ns = util.uniq_list(new_ns)
        if len(new_ns) == len(current_ns):
            return current_ns
        if len(current_ns) >= 3:
            # Hard restriction on only 3 name servers
            raise ValueError(("Adding %r would go beyond the "
                              "'3' maximum name servers") % (ns))
        self._remove_option('nameserver')
        for n in new_ns:
            self._contents.append(('option', ['nameserver', n, '']))
        return new_ns

    def _remove_option(self, opt_name):

        def remove_opt(item):
            line_type, components = item
            if line_type != 'option':
                return False
            (cfg_opt, _cfg_value, _comment_tail) = components
            if cfg_opt != opt_name:
                return False
            return True

        new_contents = []
        for c in self._contents:
            if not remove_opt(c):
                new_contents.append(c)
        self._contents = new_contents

    def add_search_domain(self, search_domain):
        flat_sds = self.search_domains
        new_sds = list(flat_sds)
        new_sds.append(str(search_domain))
        new_sds = util.uniq_list(new_sds)
        if len(flat_sds) == len(new_sds):
            return new_sds
        if len(flat_sds) >= 6:
            # Hard restriction on only 6 search domains
            raise ValueError(("Adding %r would go beyond the "
                              "'6' maximum search domains") % (search_domain))
        s_list = " ".join(new_sds)
        if len(s_list) > 256:
            # Some hard limit on 256 chars total
            raise ValueError(("Adding %r would go beyond the "
                              "256 maximum search list character limit")
                             % (search_domain))
        self._remove_option('search')
        self._contents.append(('option', ['search', s_list, '']))
        return flat_sds

    @local_domain.setter
    def local_domain(self, domain):
        self.parse()
        self._remove_option('domain')
        self._contents.append(('option', ['domain', str(domain), '']))
        return domain

    def _parse(self, contents):
        entries = []
        for (i, line) in enumerate(contents.splitlines()):
            sline = line.strip()
            if not sline:
                entries.append(('blank', [line]))
                continue
            (head, tail) = chop_comment(line, ';#')
            if not len(head.strip()):
                entries.append(('all_comment', [line]))
                continue
            if not tail:
                tail = ''
            try:
                (cfg_opt, cfg_values) = head.split(None, 1)
            except (IndexError, ValueError):
                raise IOError("Incorrectly formatted resolv.conf line %s"
                              % (i + 1))
            if cfg_opt not in ['nameserver', 'domain',
                               'search', 'sortlist', 'options']:
                raise IOError("Unexpected resolv.conf option %s" % (cfg_opt))
            entries.append(("option", [cfg_opt, cfg_values, tail]))
        return entries

# vi: ts=4 expandtab
