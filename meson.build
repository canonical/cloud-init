project(
  'cloud-init',
  version: '25.3',
  meson_version: '>=0.63.0', # rockylinux/9
  license: 'GPL-3 OR Apache-2.0',
  default_options: [
    # The default can yield broken results.
    'python.install_env=auto',
  ],
)
system = host_machine.system()
sysconfdir = get_option('sysconfdir')
init_system = get_option('init_system')

lib_exec_dir = get_option('prefix') / get_option('libexecdir') / 'cloud-init'
render_tmpl = './tools/render-template'

is_readthedocs = run_command('bash', '-c', 'echo ${READTHEDOCS}', check: true).stdout().strip()

pymod = import('python')
python = pymod.find_installation('python3')

# https://mesonbuild.com/FAQ.html#but-i-really-want-to-use-wildcards for downsteam drop-in files
find = find_program('find')

install_subdir(
  'cloudinit',
  install_dir: python.get_install_dir(),
  install_tag: 'python-runtime',
  install_mode: 'rw-r--r--',
)

# Update packaged version strings
downstream_version = get_option('downstream_version')
configure_file(
  input: 'meson_versions.py.in',
  output: 'meson_versions.py',
  configuration: {
    'UPSTREAM_VERSION': meson.project_version(),
    'DOWNSTREAM_VERSION': downstream_version,  # Optional for packagers
  },
  install_dir: python.get_install_dir()  / 'cloudinit',
  install_tag: 'python-runtime',
)


# Binaries and script entrypoints
if get_option('bash_completion') and is_readthedocs != 'True'
  bash_completions_dir = dependency('bash-completion').get_variable(
    pkgconfig: 'completionsdir',
    default_value: get_option('datadir') / 'bash-completion' / 'completions',
  )
  install_data(
    'bash_completion/cloud-init',
    install_dir: bash_completions_dir,
    install_mode: 'rw-r--r--',
    install_tag: 'bin',
  )
endif

install_data(
  [
    'tools/ds-identify',
    'tools/hook-hotplug',
    'tools/uncloud-init',
    'tools/write-ssh-key-fingerprints',
  ],
  install_dir: lib_exec_dir,
  install_mode: 'rwxr-xr-x',
  install_tag: 'bin',
)

install_data(
  ['tools/cloud-init-per', 'scripts/cloud-id', 'scripts/cloud-init'],
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
  install_tag: 'bin',
)

# Required Config and Templates
cfgs = run_command(find, 'config/cloud.cfg.d', '-type', 'f', '-name', '*.cfg', check: true)
install_data(
  ['config/cloud.cfg.d/README'] + cfgs.stdout().strip().split('\n'),
  install_dir: sysconfdir / 'cloud' / 'cloud.cfg.d',
  install_mode: 'rw-r--r--',
  install_tag: 'config',
)

distro_templates = get_option('distro_templates')
if distro_templates.length() == 0
  templates = run_command(find, 'templates', '-type', 'f', '-name', '*.tmpl', check: true).stdout().strip().split('\n')
else
  templates = []
  foreach template : distro_templates
    templates += 'templates' / template
  endforeach
endif

install_data(
  templates,
  install_dir: sysconfdir / 'cloud' / 'templates',
  install_mode: 'rw-r--r--',
  install_tag: 'config',
)

if init_system == 'systemd' and is_readthedocs != 'True'
  systemd = dependency('systemd')
  udev = dependency('udev')
  systemd_unit_dir = systemd.get_variable(pkgconfig: 'systemdsystemunitdir')
  systemd_generator_dir = systemd.get_variable(pkgconfig: 'systemdsystemgeneratordir')
  udev_dir = udev.get_variable(pkgconfig: 'udevdir')
  install_data(
    'udev/66-azure-ephemeral.rules',
    install_dir: udev_dir / 'rules.d',
    install_mode: 'rw-r--r--',
    install_tag: 'systemd',
  )

  # Must generate systemd templates in root mesonbuild, because nested
  # systemd/meson.build results in builddir @OUTPUT@ macro being doubly-nested
  # paths
  custom_target(
    input: 'systemd/cloud-init-generator.tmpl',
    output: '@BASENAME@',
    command: [
      render_tmpl,
      '@INPUT@',
      meson.current_build_dir() / '@OUTPUT@',
    ],
    install: true,
    install_dir: systemd_generator_dir,
    install_mode: 'rwxr-xr-x',
    install_tag: 'systemd',
  )

  systemd_templates = run_command(
    find,
    'systemd',
    '-not',
    '-name', '*generator*',
    '-name', '*.tmpl',
    check: true,
  )
  foreach template : systemd_templates.stdout().strip().split('\n')
    custom_target(
      input: template,
      output: '@BASENAME@',
      command: [
        render_tmpl,
        '@INPUT@',
        meson.current_build_dir() / '@OUTPUT@',
      ],
      install: true,
      install_dir: systemd_unit_dir,
      install_mode: 'rw-r--r--',
      install_tag: 'systemd',
    )
  endforeach

  if get_option('disable_sshd_keygen')
    # Typically on Fedora systems and sshd_keygen service can race cloud-init.
    install_data(
      'systemd/disable-sshd-keygen-if-cloud-init-active.conf',
      install_dir: systemd_unit_dir / 'sshd-keygen@.service.d',
      install_mode: 'rw-r--r--',
      install_tag: 'systemd',
    )
  endif

  # Allow for downstream supplements of services files meson.build changes
  install_data(
    run_command(find, 'systemd', '-name', '*.service', check: true).stdout().strip().split('\n')
    + run_command(find, 'systemd', '-name', '*.target', check: true).stdout().strip().split('\n')
    + run_command(find, 'systemd', '-name', '*.socket', check: true).stdout().strip().split('\n'),
    install_dir: systemd_unit_dir,
    install_mode: 'rw-r--r--',
    install_tag: 'systemd',
  )
elif init_system == 'sysvinit_openrc'
  openrc = dependency('openrc')
  udev = dependency('udev')
  udev_dir = udev.get_variable(pkgconfig: 'udevdir')
  install_data(
    'udev/66-azure-ephemeral.rules',
    install_dir: udev_dir / 'rules.d',
    install_mode: 'rw-r--r--',
    install_tag: 'openrc',
  )

  install_data(
    run_command(find, 'sysvinit/openrc', '-type', 'f', check: true).stdout().strip().split('\n'),
    install_dir: '/etc/init.d',
    install_mode: 'rwxr-xr-x',
    install_tag: 'openrc',
  )

  install_data(
    [
      'tools/cloud-init-hotplugd',
    ],
    install_dir: lib_exec_dir,
    install_mode: 'rwxr-xr-x',
    install_tag: 'bin',
  )
elif init_system == 'sysvinit_freebsd'
  rcd_templates = run_command(find, 'sysvinit/freebsd', '-type', 'f', check: true)
  foreach template : rcd_templates.stdout().strip().split('\n')
    custom_target(
      input: template,
      output: '@BASENAME@',
      command: [
        render_tmpl,
        '@INPUT@',
        meson.current_build_dir() / '@OUTPUT@',
      ],
      install: true,
      install_dir: sysconfdir / 'rc.d',
      install_mode: 'r-xr-xr-x',
      install_tag: 'sysvinit',
    )
  endforeach
  # Enable cloud-init on reboot
  meson.add_install_script('sh', '-c', '/usr/sbin/sysrc cloudinit_enable=YES')
endif

custom_target(
  input: 'config/cloud.cfg.tmpl',
  output: 'cloud.cfg',
  command: [
    render_tmpl,
    '--is-yaml', '@INPUT@',
    meson.current_build_dir() / '@OUTPUT@',
  ],
  install: true,
  install_dir: sysconfdir / 'cloud',
  install_mode: 'rw-r--r--',
  install_tag: 'config',
)

# Docs and Examples:
install_man(['doc/man/cloud-init.1', 'doc/man/cloud-id.1', 'doc/man/cloud-init-per.1'])
examples = run_command(find, 'doc/examples', '-name', '*.txt', '-o', '-name', '*.yaml', check: true)
install_data(
  examples.stdout().strip().split('\n'),
  install_dir: get_option('datadir') / 'doc' / 'cloud-init' / 'examples',
  install_mode: 'rw-r--r--',
  install_tag: 'doc',
)
install_data(
  [
    'doc/status.txt',
    'doc/userdata.txt',
    'doc/var-lib-cloud.txt',
  ],
  install_dir: get_option('datadir') / 'doc' / 'cloud-init',
  install_mode: 'rw-r--r--',
  install_tag: 'doc',
)
install_data(
  [
    'doc/examples/seed/README',
    'doc/examples/seed/meta-data',
    'doc/examples/seed/user-data',
  ],
  install_dir: get_option('datadir') / 'doc' / 'cloud-init' / 'examples' / 'seed',
  install_mode: 'rw-r--r--',
  install_tag: 'doc',
)

# Create expected packaging directory structure
meson.add_install_script('sh', '-c', 'mkdir -p ${DESTDIR}/' + sysconfdir + '/cloud/clean.d')

# meson setup builddir -Dinit_system=systemd
# meson test -C builddir -v
test(
  'py3',
  python,
  args: ['-m', 'pytest', meson.project_source_root() / 'tests' / 'unittests'],
  timeout: 0,
)
