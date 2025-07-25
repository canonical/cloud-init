project(
  'cloud-init',
  version: run_command('./tools/read-version', '--use-src-version', check: true).stdout().strip(),
  meson_version: '>=0.63.0', # rockylinux/9
  license: 'Dual-licensed under GPLv3 or Apache 2.0',
  default_options: [
    # The default can yield broken results.
    'python.install_env=auto',
  ],
)
system = host_machine.system()
sysconfdir = get_option('sysconfdir')
INIT_SYSTEM = get_option('init_system')

lib_exec_dir = join_paths('/usr', get_option('libexecdir'), 'cloud-init')

pymod = import('python')
python = pymod.find_installation('python3')

#https://mesonbuild.com/FAQ.html#but-i-really-want-to-use-wildcards for downsteam drop-in files
find = find_program('find')

install_subdir(
  'cloudinit',
  install_dir: python.get_install_dir(),
  install_tag: 'python',
)

completions = dependency('bash-completion')
# Binaries and script entrypoints
bash_completions_dir = completions.get_variable(
  pkgconfig: 'completionsdir',
  default_value: join_paths(get_option('datadir'), 'bash-completion', 'completions'),
)
install_data(
  'bash_completion/cloud-init',
  install_dir: bash_completions_dir,
  install_tag: 'scripts',
)

install_data(
  [
    'tools/ds-identify',
    'tools/hook-hotplug',
    'tools/uncloud-init',
    'tools/write-ssh-key-fingerprints',
  ],
  install_dir: lib_exec_dir,
  install_tag: 'scripts',
)

install_data(
  ['tools/cloud-init-per', 'scripts/cloud-id', 'scripts/cloud-init'],
  install_mode: 'rwxr-xr-x',
  install_dir: get_option('bindir'),
)

# Required Config and Templates
render_tmpl = './tools/render-template'

cfgs = run_command(find, 'config/cloud.cfg.d', '-type', 'f', '-name', '*.cfg', check: true)
install_data(
  ['config/cloud.cfg.d/README'] + cfgs.stdout().strip().split('\n'),
  install_dir: join_paths(sysconfdir, 'cloud', 'cloud.cfg.d'),
  install_tag: 'config',
)

templates = run_command(find, 'templates', '-type', 'f', '-name', '*.tmpl', check: true)
install_data(
  templates.stdout().strip().split('\n'),
  install_dir: join_paths(sysconfdir, 'cloud', 'templates'),
  install_tag: 'config',
)

if INIT_SYSTEM == 'systemd' and not readthedocs
  systemd = dependency('systemd')
  udev = dependency('udev')
  systemd_unit_dir = systemd.get_variable(pkgconfig: 'systemdsystemunitdir')
  systemd_generator_dir = systemd.get_variable(pkgconfig: 'systemdsystemgeneratordir')
  udev_dir = udev.get_variable(pkgconfig: 'udevdir', default_value: '/usr/lib/udev')
  install_data(
    'udev/66-azure-ephemeral.rules',
    install_dir: join_paths(udev_dir, 'rules.d'),
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
      join_paths(meson.current_build_dir(), '@OUTPUT@'),
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
        join_paths(meson.current_build_dir(), '@OUTPUT@'),
      ],
      install: true,
      install_dir: systemd_unit_dir,
      install_tag: 'systemd',
    )
  endforeach

  install_data(
    'systemd/disable-sshd-keygen-if-cloud-init-active.conf',
    install_dir: join_paths(systemd_unit_dir, 'sshd-keygen@.service.d'),
    install_tag: 'systemd',
  )

  # Allow for downstream supplements of services files meson.build changes
  install_data(
    run_command(find, 'systemd', '-name', '*.service', check: true).stdout().strip().split('\n')
    + run_command(find, 'systemd', '-name', '*.target', check: true).stdout().strip().split('\n')
    + run_command(find, 'systemd', '-name', '*.socket', check: true).stdout().strip().split('\n'),
    install_dir: systemd_unit_dir,
    install_tag: 'systemd',
  )
endif

custom_target(
  input: 'config/cloud.cfg.tmpl',
  output: 'cloud.cfg',
  command: [
    render_tmpl,
    '--is-yaml', '@INPUT@',
    join_paths(meson.current_build_dir(), '@OUTPUT@'),
  ],
  install: true,
  install_dir: join_paths(sysconfdir, 'cloud'),
  install_tag: 'config',
)

# Docs and Examples:
install_man(['doc/man/cloud-init.1', 'doc/man/cloud-id.1', 'doc/man/cloud-init-per.1'])
examples = run_command(find, 'doc/examples', '-name', '*.txt', '-o', '-name', '*.yaml', check: true)
install_data(
  examples.stdout().strip().split('\n'),
  install_dir: join_paths(get_option('datadir'), 'doc', 'cloud-init', 'examples'),
  install_tag: 'docs',
)
install_data(
  [
    'doc/examples/seed/README',
    'doc/examples/seed/meta-data',
    'doc/examples/seed/user-data',
  ],
  install_dir: join_paths(get_option('datadir'), 'doc', 'cloud-init', 'examples', 'seed'),
  install_tag: 'docs',
)

# meson setup ../builddir -Dinit_system=systemd
# meson compile -C ../builddir
# meson test -C ../builddir -v
test(
  'py3',
  python,
  args: ['-m', 'pytest', meson.project_source_root() / 'tests' / 'unittests'],
  timeout: 0,
)