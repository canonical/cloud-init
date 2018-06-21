# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Apt Configure
-------------
**Summary:** configure apt

This module handles both configuration of apt options and adding source lists.
There are configuration options such as ``apt_get_wrapper`` and
``apt_get_command`` that control how cloud-init invokes apt-get.
These configuration options are handled on a per-distro basis, so consult
documentation for cloud-init's distro support for instructions on using
these config options.

.. note::
    To ensure that apt configuration is valid yaml, any strings containing
    special characters, especially ``:`` should be quoted.

.. note::
    For more information about apt configuration, see the
    ``Additional apt configuration`` example.

**Preserve sources.list:**

By default, cloud-init will generate a new sources list in
``/etc/apt/sources.list.d`` based on any changes specified in cloud config.
To disable this behavior and preserve the sources list from the pristine image,
set ``preserve_sources_list`` to ``true``.

.. note::
    The ``preserve_sources_list`` option overrides all other config keys that
    would alter ``sources.list`` or ``sources.list.d``, **except** for
    additional sources to be added to ``sources.list.d``.

**Disable source suites:**

Entries in the sources list can be disabled using ``disable_suites``, which
takes a list of suites to be disabled. If the string ``$RELEASE`` is present in
a suite in the ``disable_suites`` list, it will be replaced with the release
name. If a suite specified in ``disable_suites`` is not present in
``sources.list`` it will be ignored. For convenience, several aliases are
provided for ``disable_suites``:

    - ``updates`` => ``$RELEASE-updates``
    - ``backports`` => ``$RELEASE-backports``
    - ``security`` => ``$RELEASE-security``
    - ``proposed`` => ``$RELEASE-proposed``
    - ``release`` => ``$RELEASE``

.. note::
    When a suite is disabled using ``disable_suites``, its entry in
    ``sources.list`` is not deleted; it is just commented out.

**Configure primary and security mirrors:**

The primary and security archive mirrors can be specified using the ``primary``
and ``security`` keys, respectively. Both the ``primary`` and ``security`` keys
take a list of configs, allowing mirrors to be specified on a per-architecture
basis. Each config is a dictionary which must have an entry for ``arches``,
specifying which architectures that config entry is for. The keyword
``default`` applies to any architecture not explicitly listed. The mirror url
can be specified with the ``uri`` key, or a list of mirrors to check can be
provided in order, with the first mirror that can be resolved being selected.
This allows the same configuration to be used in different environment, with
different hosts used for a local apt mirror. If no mirror is provided by
``uri`` or ``search``, ``search_dns`` may be used to search for dns names in
the format ``<distro>-mirror`` in each of the following:

    - fqdn of this host per cloud metadata
    - localdomain
    - domains listed in ``/etc/resolv.conf``

If there is a dns entry for ``<distro>-mirror``, then it is assumed that there
is a distro mirror at ``http://<distro>-mirror.<domain>/<distro>``. If the
``primary`` key is defined, but not the ``security`` key, then then
configuration for ``primary`` is also used for ``security``. If ``search_dns``
is used for the ``security`` key, the search pattern will be.
``<distro>-security-mirror``.

If no mirrors are specified, or all lookups fail, then default mirrors defined
in the datasource are used. If none are present in the datasource either the
following defaults are used:

    - primary: ``http://archive.ubuntu.com/ubuntu``
    - security: ``http://security.ubuntu.com/ubuntu``

**Specify sources.list template:**

A custom template for rendering ``sources.list`` can be specefied with
``sources_list``. If no ``sources_list`` template is given, cloud-init will
use sane default. Within this template, the following strings will be replaced
with the appropriate values:

    - ``$MIRROR``
    - ``$RELEASE``
    - ``$PRIMARY``
    - ``$SECURITY``

**Pass configuration to apt:**

Apt configuration can be specified using ``conf``. Configuration is specified
as a string. For multiline apt configuration, make sure to follow yaml syntax.

**Configure apt proxy:**

Proxy configuration for apt can be specified using ``conf``, but proxy config
keys also exist for convenience. The proxy config keys, ``http_proxy``,
``ftp_proxy``, and ``https_proxy`` may be used to specify a proxy for http, ftp
and https protocols respectively. The ``proxy`` key also exists as an alias for
``http_proxy``. Proxy url is specified in the format
``<protocol>://[[user][:pass]@]host[:port]/``.

**Add apt repos by regex:**

All source entries in ``apt-sources`` that match regex in
``add_apt_repo_match`` will be added to the system using
``add-apt-repository``. If ``add_apt_repo_match`` is not specified, it defaults
to ``^[\\w-]+:\\w``

**Add source list entries:**

Source list entries can be specified as a dictionary under the ``sources``
config key, with key in the dict representing a different source file. The key
The key of each source entry will be used as an id that can be referenced in
other config entries, as well as the filename for the source's configuration
under ``/etc/apt/sources.list.d``. If the name does not end with ``.list``,
it will be appended. If there is no configuration for a key in ``sources``, no
file will be written, but the key may still be referred to as an id in other
``sources`` entries.

Each entry under ``sources`` is a dictionary which may contain any of the
following optional keys:

    - ``source``: a sources.list entry (some variable replacements apply)
    - ``keyid``: a key to import via shortid or fingerprint
    - ``key``: a raw PGP key
    - ``keyserver``: alternate keyserver to pull ``keyid`` key from

The ``source`` key supports variable replacements for the following strings:

    - ``$MIRROR``
    - ``$PRIMARY``
    - ``$SECURITY``
    - ``$RELEASE``

**Internal name:** ``cc_apt_configure``

**Module frequency:** per instance

**Supported distros:** ubuntu, debian

**Config keys**::

    apt:
        preserve_sources_list: <true/false>
        disable_suites:
            - $RELEASE-updates
            - backports
            - $RELEASE
            - mysuite
        primary:
            - arches:
                - amd64
                - i386
                - default
              uri: "http://us.archive.ubuntu.com/ubuntu"
              search:
                - "http://cool.but-sometimes-unreachable.com/ubuntu"
                - "http://us.archive.ubuntu.com/ubuntu"
              search_dns: <true/false>
            - arches:
                - s390x
                - arm64
              uri: "http://archive-to-use-for-arm64.example.com/ubuntu"
        security:
            - arches:
                - default
              search_dns: true
        sources_list: |
            deb $MIRROR $RELEASE main restricted
            deb-src $MIRROR $RELEASE main restricted
            deb $PRIMARY $RELEASE universe restricted
            deb $SECURITY $RELEASE-security multiverse
        debconf_selections:
            set1: the-package the-package/some-flag boolean true
        conf: |
            APT {
                Get {
                    Assume-Yes "true";
                    Fix-Broken "true";
                }
            }
        proxy: "http://[[user][:pass]@]host[:port]/"
        http_proxy: "http://[[user][:pass]@]host[:port]/"
        ftp_proxy: "ftp://[[user][:pass]@]host[:port]/"
        https_proxy: "https://[[user][:pass]@]host[:port]/"
        sources:
            source1:
                keyid: "keyid"
                keyserver: "keyserverurl"
                source: "deb http://<url>/ xenial main"
            source2:
                source: "ppa:<ppa-name>"
            source3:
                source: "deb $MIRROR $RELEASE multiverse"
                key: |
                    ------BEGIN PGP PUBLIC KEY BLOCK-------
                    <key data>
                    ------END PGP PUBLIC KEY BLOCK-------
"""

import glob
import os
import re

from cloudinit import gpg
from cloudinit import log as logging
from cloudinit import templater
from cloudinit import util

LOG = logging.getLogger(__name__)

# this will match 'XXX:YYY' (ie, 'cloud-archive:foo' or 'ppa:bar')
ADD_APT_REPO_MATCH = r"^[\w-]+:\w"

# place where apt stores cached repository data
APT_LISTS = "/var/lib/apt/lists"

# Files to store proxy information
APT_CONFIG_FN = "/etc/apt/apt.conf.d/94cloud-init-config"
APT_PROXY_FN = "/etc/apt/apt.conf.d/90cloud-init-aptproxy"

# Default keyserver to use
DEFAULT_KEYSERVER = "keyserver.ubuntu.com"

# Default archive mirrors
PRIMARY_ARCH_MIRRORS = {"PRIMARY": "http://archive.ubuntu.com/ubuntu/",
                        "SECURITY": "http://security.ubuntu.com/ubuntu/"}
PORTS_MIRRORS = {"PRIMARY": "http://ports.ubuntu.com/ubuntu-ports",
                 "SECURITY": "http://ports.ubuntu.com/ubuntu-ports"}
PRIMARY_ARCHES = ['amd64', 'i386']
PORTS_ARCHES = ['s390x', 'arm64', 'armhf', 'powerpc', 'ppc64el']


def get_default_mirrors(arch=None, target=None):
    """returns the default mirrors for the target. These depend on the
       architecture, for more see:
       https://wiki.ubuntu.com/UbuntuDevelopment/PackageArchive#Ports"""
    if arch is None:
        arch = util.get_architecture(target)
    if arch in PRIMARY_ARCHES:
        return PRIMARY_ARCH_MIRRORS.copy()
    if arch in PORTS_ARCHES:
        return PORTS_MIRRORS.copy()
    raise ValueError("No default mirror known for arch %s" % arch)


def handle(name, ocfg, cloud, log, _):
    """process the config for apt_config. This can be called from
       curthooks if a global apt config was provided or via the "apt"
       standalone command."""
    # keeping code close to curtin codebase via entry handler
    target = None
    if log is not None:
        global LOG
        LOG = log
    # feed back converted config, but only work on the subset under 'apt'
    ocfg = convert_to_v3_apt_format(ocfg)
    cfg = ocfg.get('apt', {})

    if not isinstance(cfg, dict):
        raise ValueError(
            "Expected dictionary for 'apt' config, found {config_type}".format(
                config_type=type(cfg)))

    apply_debconf_selections(cfg, target)
    apply_apt(cfg, cloud, target)


def _should_configure_on_empty_apt():
    # if no config was provided, should apt configuration be done?
    if util.system_is_snappy():
        return False, "system is snappy."
    if not (util.which('apt-get') or util.which('apt')):
        return False, "no apt commands."
    return True, "Apt is available."


def apply_apt(cfg, cloud, target):
    # cfg is the 'apt' top level dictionary already in 'v3' format.
    if not cfg:
        should_config, msg = _should_configure_on_empty_apt()
        if not should_config:
            LOG.debug("Nothing to do: No apt config and %s", msg)
            return

    LOG.debug("handling apt config: %s", cfg)

    release = util.lsb_release(target=target)['codename']
    arch = util.get_architecture(target)
    mirrors = find_apt_mirror_info(cfg, cloud, arch=arch)
    LOG.debug("Apt Mirror info: %s", mirrors)

    if util.is_false(cfg.get('preserve_sources_list', False)):
        generate_sources_list(cfg, release, mirrors, cloud)
        rename_apt_lists(mirrors, target)

    try:
        apply_apt_config(cfg, APT_PROXY_FN, APT_CONFIG_FN)
    except (IOError, OSError):
        LOG.exception("Failed to apply proxy or apt config info:")

    # Process 'apt_source -> sources {dict}'
    if 'sources' in cfg:
        params = mirrors
        params['RELEASE'] = release
        params['MIRROR'] = mirrors["MIRROR"]

        matcher = None
        matchcfg = cfg.get('add_apt_repo_match', ADD_APT_REPO_MATCH)
        if matchcfg:
            matcher = re.compile(matchcfg).search

        add_apt_sources(cfg['sources'], cloud, target=target,
                        template_params=params, aa_repo_match=matcher)


def debconf_set_selections(selections, target=None):
    util.subp(['debconf-set-selections'], data=selections, target=target,
              capture=True)


def dpkg_reconfigure(packages, target=None):
    # For any packages that are already installed, but have preseed data
    # we populate the debconf database, but the filesystem configuration
    # would be preferred on a subsequent dpkg-reconfigure.
    # so, what we have to do is "know" information about certain packages
    # to unconfigure them.
    unhandled = []
    to_config = []
    for pkg in packages:
        if pkg in CONFIG_CLEANERS:
            LOG.debug("unconfiguring %s", pkg)
            CONFIG_CLEANERS[pkg](target)
            to_config.append(pkg)
        else:
            unhandled.append(pkg)

    if len(unhandled):
        LOG.warning("The following packages were installed and preseeded, "
                    "but cannot be unconfigured: %s", unhandled)

    if len(to_config):
        util.subp(['dpkg-reconfigure', '--frontend=noninteractive'] +
                  list(to_config), data=None, target=target, capture=True)


def apply_debconf_selections(cfg, target=None):
    """apply_debconf_selections - push content to debconf"""
    # debconf_selections:
    #  set1: |
    #   cloud-init cloud-init/datasources multiselect MAAS
    #  set2: pkg pkg/value string bar
    selsets = cfg.get('debconf_selections')
    if not selsets:
        LOG.debug("debconf_selections was not set in config")
        return

    selections = '\n'.join(
        [selsets[key] for key in sorted(selsets.keys())])
    debconf_set_selections(selections.encode() + b"\n", target=target)

    # get a complete list of packages listed in input
    pkgs_cfgd = set()
    for _key, content in selsets.items():
        for line in content.splitlines():
            if line.startswith("#"):
                continue
            pkg = re.sub(r"[:\s].*", "", line)
            pkgs_cfgd.add(pkg)

    pkgs_installed = util.get_installed_packages(target)

    LOG.debug("pkgs_cfgd: %s", pkgs_cfgd)
    need_reconfig = pkgs_cfgd.intersection(pkgs_installed)

    if len(need_reconfig) == 0:
        LOG.debug("no need for reconfig")
        return

    dpkg_reconfigure(need_reconfig, target=target)


def clean_cloud_init(target):
    """clean out any local cloud-init config"""
    flist = glob.glob(
        util.target_path(target, "/etc/cloud/cloud.cfg.d/*dpkg*"))

    LOG.debug("cleaning cloud-init config from: %s", flist)
    for dpkg_cfg in flist:
        os.unlink(dpkg_cfg)


def mirrorurl_to_apt_fileprefix(mirror):
    """mirrorurl_to_apt_fileprefix
       Convert a mirror url to the file prefix used by apt on disk to
       store cache information for that mirror.
       To do so do:
       - take off ???://
       - drop tailing /
       - convert in string / to _"""
    string = mirror
    if string.endswith("/"):
        string = string[0:-1]
    pos = string.find("://")
    if pos >= 0:
        string = string[pos + 3:]
    string = string.replace("/", "_")
    return string


def rename_apt_lists(new_mirrors, target=None):
    """rename_apt_lists - rename apt lists to preserve old cache data"""
    default_mirrors = get_default_mirrors(util.get_architecture(target))

    pre = util.target_path(target, APT_LISTS)
    for (name, omirror) in default_mirrors.items():
        nmirror = new_mirrors.get(name)
        if not nmirror:
            continue

        oprefix = pre + os.path.sep + mirrorurl_to_apt_fileprefix(omirror)
        nprefix = pre + os.path.sep + mirrorurl_to_apt_fileprefix(nmirror)
        if oprefix == nprefix:
            continue
        olen = len(oprefix)
        for filename in glob.glob("%s_*" % oprefix):
            newname = "%s%s" % (nprefix, filename[olen:])
            LOG.debug("Renaming apt list %s to %s", filename, newname)
            try:
                os.rename(filename, newname)
            except OSError:
                # since this is a best effort task, warn with but don't fail
                LOG.warning("Failed to rename apt list:", exc_info=True)


def mirror_to_placeholder(tmpl, mirror, placeholder):
    """mirror_to_placeholder
       replace the specified mirror in a template with a placeholder string
       Checks for existance of the expected mirror and warns if not found"""
    if mirror not in tmpl:
        LOG.warning("Expected mirror '%s' not found in: %s", mirror, tmpl)
    return tmpl.replace(mirror, placeholder)


def map_known_suites(suite):
    """there are a few default names which will be auto-extended.
       This comes at the inability to use those names literally as suites,
       but on the other hand increases readability of the cfg quite a lot"""
    mapping = {'updates': '$RELEASE-updates',
               'backports': '$RELEASE-backports',
               'security': '$RELEASE-security',
               'proposed': '$RELEASE-proposed',
               'release': '$RELEASE'}
    try:
        retsuite = mapping[suite]
    except KeyError:
        retsuite = suite
    return retsuite


def disable_suites(disabled, src, release):
    """reads the config for suites to be disabled and removes those
       from the template"""
    if not disabled:
        return src

    retsrc = src
    for suite in disabled:
        suite = map_known_suites(suite)
        releasesuite = templater.render_string(suite, {'RELEASE': release})
        LOG.debug("Disabling suite %s as %s", suite, releasesuite)

        newsrc = ""
        for line in retsrc.splitlines(True):
            if line.startswith("#"):
                newsrc += line
                continue

            # sources.list allow options in cols[1] which can have spaces
            # so the actual suite can be [2] or later. example:
            # deb [ arch=amd64,armel k=v ] http://example.com/debian
            cols = line.split()
            if len(cols) > 1:
                pcol = 2
                if cols[1].startswith("["):
                    for col in cols[1:]:
                        pcol += 1
                        if col.endswith("]"):
                            break

                if cols[pcol] == releasesuite:
                    line = '# suite disabled by cloud-init: %s' % line
            newsrc += line
        retsrc = newsrc

    return retsrc


def generate_sources_list(cfg, release, mirrors, cloud):
    """generate_sources_list
       create a source.list file based on a custom or default template
       by replacing mirrors and release in the template"""
    aptsrc = "/etc/apt/sources.list"
    params = {'RELEASE': release, 'codename': release}
    for k in mirrors:
        params[k] = mirrors[k]
        params[k.lower()] = mirrors[k]

    tmpl = cfg.get('sources_list', None)
    if tmpl is None:
        LOG.info("No custom template provided, fall back to builtin")
        template_fn = cloud.get_template_filename('sources.list.%s' %
                                                  (cloud.distro.name))
        if not template_fn:
            template_fn = cloud.get_template_filename('sources.list')
        if not template_fn:
            LOG.warning("No template found, "
                        "not rendering /etc/apt/sources.list")
            return
        tmpl = util.load_file(template_fn)

    rendered = templater.render_string(tmpl, params)
    disabled = disable_suites(cfg.get('disable_suites'), rendered, release)
    util.write_file(aptsrc, disabled, mode=0o644)


def add_apt_key_raw(key, target=None):
    """
    actual adding of a key as defined in key argument
    to the system
    """
    LOG.debug("Adding key:\n'%s'", key)
    try:
        util.subp(['apt-key', 'add', '-'], data=key.encode(), target=target)
    except util.ProcessExecutionError:
        LOG.exception("failed to add apt GPG Key to apt keyring")
        raise


def add_apt_key(ent, target=None):
    """
    Add key to the system as defined in ent (if any).
    Supports raw keys or keyid's
    The latter will as a first step fetched to get the raw key
    """
    if 'keyid' in ent and 'key' not in ent:
        keyserver = DEFAULT_KEYSERVER
        if 'keyserver' in ent:
            keyserver = ent['keyserver']

        ent['key'] = gpg.getkeybyid(ent['keyid'], keyserver)

    if 'key' in ent:
        add_apt_key_raw(ent['key'], target)


def update_packages(cloud):
    cloud.distro.update_package_sources()


def add_apt_sources(srcdict, cloud, target=None, template_params=None,
                    aa_repo_match=None):
    """
    add entries in /etc/apt/sources.list.d for each abbreviated
    sources.list entry in 'srcdict'.  When rendering template, also
    include the values in dictionary searchList
    """
    if template_params is None:
        template_params = {}

    if aa_repo_match is None:
        raise ValueError('did not get a valid repo matcher')

    if not isinstance(srcdict, dict):
        raise TypeError('unknown apt format: %s' % (srcdict))

    for filename in srcdict:
        ent = srcdict[filename]
        LOG.debug("adding source/key '%s'", ent)
        if 'filename' not in ent:
            ent['filename'] = filename

        add_apt_key(ent, target)

        if 'source' not in ent:
            continue
        source = ent['source']
        source = templater.render_string(source, template_params)

        if not ent['filename'].startswith("/"):
            ent['filename'] = os.path.join("/etc/apt/sources.list.d/",
                                           ent['filename'])
        if not ent['filename'].endswith(".list"):
            ent['filename'] += ".list"

        if aa_repo_match(source):
            try:
                util.subp(["add-apt-repository", source], target=target)
            except util.ProcessExecutionError:
                LOG.exception("add-apt-repository failed.")
                raise
            continue

        sourcefn = util.target_path(target, ent['filename'])
        try:
            contents = "%s\n" % (source)
            util.write_file(sourcefn, contents, omode="a")
        except IOError as detail:
            LOG.exception("failed write to file %s: %s", sourcefn, detail)
            raise

    update_packages(cloud)

    return


def convert_v1_to_v2_apt_format(srclist):
    """convert v1 apt format to v2 (dict in apt_sources)"""
    srcdict = {}
    if isinstance(srclist, list):
        LOG.debug("apt config: convert V1 to V2 format (source list to dict)")
        for srcent in srclist:
            if 'filename' not in srcent:
                # file collides for multiple !filename cases for compatibility
                # yet we need them all processed, so not same dictionary key
                srcent['filename'] = "cloud_config_sources.list"
                key = util.rand_dict_key(srcdict, "cloud_config_sources.list")
            else:
                # all with filename use that as key (matching new format)
                key = srcent['filename']
            srcdict[key] = srcent
    elif isinstance(srclist, dict):
        srcdict = srclist
    else:
        raise ValueError("unknown apt_sources format")

    return srcdict


def convert_key(oldcfg, aptcfg, oldkey, newkey):
    """convert an old key to the new one if the old one exists
       returns true if a key was found and converted"""
    if oldcfg.get(oldkey, None) is not None:
        aptcfg[newkey] = oldcfg.get(oldkey)
        del oldcfg[oldkey]
        return True
    return False


def convert_mirror(oldcfg, aptcfg):
    """convert old apt_mirror keys into the new more advanced mirror spec"""
    keymap = [('apt_mirror', 'uri'),
              ('apt_mirror_search', 'search'),
              ('apt_mirror_search_dns', 'search_dns')]
    converted = False
    newmcfg = {'arches': ['default']}
    for oldkey, newkey in keymap:
        if convert_key(oldcfg, newmcfg, oldkey, newkey):
            converted = True

    # only insert new style config if anything was converted
    if converted:
        aptcfg['primary'] = [newmcfg]


def convert_v2_to_v3_apt_format(oldcfg):
    """convert old to new keys and adapt restructured mirror spec"""
    mapoldkeys = {'apt_sources': 'sources',
                  'apt_mirror': None,
                  'apt_mirror_search': None,
                  'apt_mirror_search_dns': None,
                  'apt_proxy': 'proxy',
                  'apt_http_proxy': 'http_proxy',
                  'apt_ftp_proxy': 'https_proxy',
                  'apt_https_proxy': 'ftp_proxy',
                  'apt_preserve_sources_list': 'preserve_sources_list',
                  'apt_custom_sources_list': 'sources_list',
                  'add_apt_repo_match': 'add_apt_repo_match'}
    needtoconvert = []
    for oldkey in mapoldkeys:
        if oldkey in oldcfg:
            if oldcfg[oldkey] in (None, ""):
                del oldcfg[oldkey]
            else:
                needtoconvert.append(oldkey)

    # no old config, so no new one to be created
    if not needtoconvert:
        return oldcfg
    LOG.debug("apt config: convert V2 to V3 format for keys '%s'",
              ", ".join(needtoconvert))

    # if old AND new config are provided, prefer the new one (LP #1616831)
    newaptcfg = oldcfg.get('apt', None)
    if newaptcfg is not None:
        LOG.debug("apt config: V1/2 and V3 format specified, preferring V3")
        for oldkey in needtoconvert:
            newkey = mapoldkeys[oldkey]
            verify = oldcfg[oldkey]  # drop, but keep a ref for verification
            del oldcfg[oldkey]
            if newkey is None or newaptcfg.get(newkey, None) is None:
                # no simple mapping or no collision on this particular key
                continue
            if verify != newaptcfg[newkey]:
                raise ValueError("Old and New apt format defined with unequal "
                                 "values %s vs %s @ %s" % (verify,
                                                           newaptcfg[newkey],
                                                           oldkey))
        # return conf after clearing conflicting V1/2 keys
        return oldcfg

    # create new format from old keys
    aptcfg = {}

    # simple renames / moves under the apt key
    for oldkey in mapoldkeys:
        if mapoldkeys[oldkey] is not None:
            convert_key(oldcfg, aptcfg, oldkey, mapoldkeys[oldkey])

    # mirrors changed in a more complex way
    convert_mirror(oldcfg, aptcfg)

    for oldkey in mapoldkeys:
        if oldcfg.get(oldkey, None) is not None:
            raise ValueError("old apt key '%s' left after conversion" % oldkey)

    # insert new format into config and return full cfg with only v3 content
    oldcfg['apt'] = aptcfg
    return oldcfg


def convert_to_v3_apt_format(cfg):
    """convert the old list based format to the new dict based one. After that
       convert the old dict keys/format to v3 a.k.a 'new apt config'"""
    # V1 -> V2, the apt_sources entry from list to dict
    apt_sources = cfg.get('apt_sources', None)
    if apt_sources is not None:
        cfg['apt_sources'] = convert_v1_to_v2_apt_format(apt_sources)

    # V2 -> V3, move all former globals under the "apt" key
    # Restructure into new key names and mirror hierarchy
    cfg = convert_v2_to_v3_apt_format(cfg)

    return cfg


def search_for_mirror(candidates):
    """
    Search through a list of mirror urls for one that works
    This needs to return quickly.
    """
    if candidates is None:
        return None

    LOG.debug("search for mirror in candidates: '%s'", candidates)
    for cand in candidates:
        try:
            if util.is_resolvable_url(cand):
                LOG.debug("found working mirror: '%s'", cand)
                return cand
        except Exception:
            pass
    return None


def search_for_mirror_dns(configured, mirrortype, cfg, cloud):
    """
    Try to resolve a list of predefines DNS names to pick mirrors
    """
    mirror = None

    if configured:
        mydom = ""
        doms = []

        if mirrortype == "primary":
            mirrordns = "mirror"
        elif mirrortype == "security":
            mirrordns = "security-mirror"
        else:
            raise ValueError("unknown mirror type")

        # if we have a fqdn, then search its domain portion first
        (_, fqdn) = util.get_hostname_fqdn(cfg, cloud)
        mydom = ".".join(fqdn.split(".")[1:])
        if mydom:
            doms.append(".%s" % mydom)

        doms.extend((".localdomain", "",))

        mirror_list = []
        distro = cloud.distro.name
        mirrorfmt = "http://%s-%s%s/%s" % (distro, mirrordns, "%s", distro)
        for post in doms:
            mirror_list.append(mirrorfmt % (post))

        mirror = search_for_mirror(mirror_list)

    return mirror


def update_mirror_info(pmirror, smirror, arch, cloud):
    """sets security mirror to primary if not defined.
       returns defaults if no mirrors are defined"""
    if pmirror is not None:
        if smirror is None:
            smirror = pmirror
        return {'PRIMARY': pmirror,
                'SECURITY': smirror}

    # None specified at all, get default mirrors from cloud
    mirror_info = cloud.datasource.get_package_mirror_info()
    if mirror_info:
        # get_package_mirror_info() returns a dictionary with
        # arbitrary key/value pairs including 'primary' and 'security' keys.
        # caller expects dict with PRIMARY and SECURITY.
        m = mirror_info.copy()
        m['PRIMARY'] = m['primary']
        m['SECURITY'] = m['security']

        return m

    # if neither apt nor cloud configured mirrors fall back to
    return get_default_mirrors(arch)


def get_arch_mirrorconfig(cfg, mirrortype, arch):
    """out of a list of potential mirror configurations select
       and return the one matching the architecture (or default)"""
    # select the mirror specification (if-any)
    mirror_cfg_list = cfg.get(mirrortype, None)
    if mirror_cfg_list is None:
        return None

    # select the specification matching the target arch
    default = None
    for mirror_cfg_elem in mirror_cfg_list:
        arches = mirror_cfg_elem.get("arches")
        if arch in arches:
            return mirror_cfg_elem
        if "default" in arches:
            default = mirror_cfg_elem
    return default


def get_mirror(cfg, mirrortype, arch, cloud):
    """pass the three potential stages of mirror specification
       returns None is neither of them found anything otherwise the first
       hit is returned"""
    mcfg = get_arch_mirrorconfig(cfg, mirrortype, arch)
    if mcfg is None:
        return None

    # directly specified
    mirror = mcfg.get("uri", None)

    # fallback to search if specified
    if mirror is None:
        # list of mirrors to try to resolve
        mirror = search_for_mirror(mcfg.get("search", None))

    # fallback to search_dns if specified
    if mirror is None:
        # list of mirrors to try to resolve
        mirror = search_for_mirror_dns(mcfg.get("search_dns", None),
                                       mirrortype, cfg, cloud)

    return mirror


def find_apt_mirror_info(cfg, cloud, arch=None):
    """find_apt_mirror_info
       find an apt_mirror given the cfg provided.
       It can check for separate config of primary and security mirrors
       If only primary is given security is assumed to be equal to primary
       If the generic apt_mirror is given that is defining for both
    """

    if arch is None:
        arch = util.get_architecture()
        LOG.debug("got arch for mirror selection: %s", arch)
    pmirror = get_mirror(cfg, "primary", arch, cloud)
    LOG.debug("got primary mirror: %s", pmirror)
    smirror = get_mirror(cfg, "security", arch, cloud)
    LOG.debug("got security mirror: %s", smirror)

    mirror_info = update_mirror_info(pmirror, smirror, arch, cloud)

    # less complex replacements use only MIRROR, derive from primary
    mirror_info["MIRROR"] = mirror_info["PRIMARY"]

    return mirror_info


def apply_apt_config(cfg, proxy_fname, config_fname):
    """apply_apt_config
       Applies any apt*proxy config from if specified
    """
    # Set up any apt proxy
    cfgs = (('proxy', 'Acquire::http::Proxy "%s";'),
            ('http_proxy', 'Acquire::http::Proxy "%s";'),
            ('ftp_proxy', 'Acquire::ftp::Proxy "%s";'),
            ('https_proxy', 'Acquire::https::Proxy "%s";'))

    proxies = [fmt % cfg.get(name) for (name, fmt) in cfgs if cfg.get(name)]
    if len(proxies):
        LOG.debug("write apt proxy info to %s", proxy_fname)
        util.write_file(proxy_fname, '\n'.join(proxies) + '\n')
    elif os.path.isfile(proxy_fname):
        util.del_file(proxy_fname)
        LOG.debug("no apt proxy configured, removed %s", proxy_fname)

    if cfg.get('conf', None):
        LOG.debug("write apt config info to %s", config_fname)
        util.write_file(config_fname, cfg.get('conf'))
    elif os.path.isfile(config_fname):
        util.del_file(config_fname)
        LOG.debug("no apt config configured, removed %s", config_fname)


CONFIG_CLEANERS = {
    'cloud-init': clean_cloud_init,
}

# vi: ts=4 expandtab
