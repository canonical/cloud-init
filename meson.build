project(
    'cloud-init',
    version: run_command('./tools/read-version', check: true).stdout().strip(),
    meson_version: '>=1.0.0',
    default_options: [
      # The default can yield broken results.
      'python.install_env=auto'
    ]
)

completions = dependency('bash-completion')
systemd = dependency('systemd')
udev = dependency('udev')
system = host_machine.system()

pkgdatadir = get_option('datadir')
sysconfdir = get_option('sysconfdir')

# TODO(Add support for discovery and install of BSD, sysvinit, openrc)
BSD_SYSTEMS = ['dragonfly', 'freebsd', 'netbsd', 'openbsd']
lib_exec_dir = join_paths('/usr', 'lib', 'cloud-init')
if system in BSD_SYSTEMS
  INIT_SYSTEM = 'sysvinit_freebsd'
else
  INIT_SYSTEM = 'systemd'
  if system in ['redhat']
    lib_exec_dir = join_paths('/usr', get_option('libexecdir'), 'cloud-init')
  endif
endif

pymod = import('python')
python = pymod.find_installation('python3')
python.dependency()

find = find_program('find')
py_sources = run_command(find, 'cloudinit', '-name', '*.py', check: true).stdout().strip().split('\n')
py_sources_files = files(py_sources)

# RELEASE_BLOCKER preserve_path unsupported meson < 0.63.0
python.install_sources(py_sources, preserve_path: true)

bash_completions_dir = completions.get_variable(
  pkgconfig: 'completionsdir', default_value: '/etc/bash_completion.d')

foreach script: ['tools/ds-identify', 'tools/hook-hotplug','tools/uncloud-init', 'tools/write-ssh-key-fingerprints' ]
  install_data(
    script, install_dir: lib_exec_dir)
endforeach


# Scripts
install_data(
  'tools/cloud-init-per',
  install_mode: 'rwxr-xr-x',
  install_dir: get_option('bindir'),
)
install_data(
  'tools/cloud-init.script',
  rename: 'cloud-init',
  install_mode: 'rwxr-xr-x',
  install_dir: get_option('bindir'),
)
install_data(
  'tools/cloud-id.script',
  rename: 'cloud-id',
  install_mode: 'rwxr-xr-x',
  install_dir: get_option('bindir'),
)

# Required Config and Templates
render_tmpl = './tools/render-template'
subdir('config/cloud.cfg.d')
subdir('templates')

if INIT_SYSTEM == 'systemd'
  systemd_unit_dir =  systemd.get_variable(
    pkgconfig: 'systemdsystemunitdir'
  )
  systemd_generator_dir =  systemd.get_variable(
    pkgconfig: 'systemdsystemgeneratordir'
  )
  subdir('systemd')
  udev_dir = udev.get_variable(
    pkgconfig: 'udevdir', default_value: '/usr/lib/udev'
  )
  install_data(
    'udev/66-azure-ephemeral.rules',
    install_dir: join_paths(udev_dir, 'rules.d'),
    install_tag: 'systemd'
  )

  # Must generate systemd templates in root mesonbuild, because nested
  # systemd/meson.build results in builddir @OUTPUT@ macro being doubly-nested
  # paths
  systemd_templates = run_command(find, 'systemd', '-name', '*.tmpl', check: true).stdout().strip().split('\n')
  foreach template: systemd_templates
    # RELEASE_BLOCKER substring 'in' only supported meson < 1.0.0
    if 'generator' in template
      dir = systemd_generator_dir
    else
      dir = systemd_unit_dir
    endif
    custom_target(
      input: template,
      output: '@BASENAME@',
      command: [render_tmpl, '@INPUT@', join_paths(meson.current_build_dir(), '@OUTPUT@')],
      install: true,
      install_dir: dir,
      install_tag: 'systemd'
    )
  endforeach
endif

custom_target(
  input: 'config/cloud.cfg.tmpl',
  output: 'cloud.cfg',
  command: [render_tmpl, '--is-yaml', '@INPUT@', join_paths(meson.current_build_dir(), '@OUTPUT@')],
  install: true,
  install_dir: join_paths(sysconfdir, 'cloud'),
  install_tag: 'config'
)


# Docs and Examples:
subdir('doc/examples')
mandir = get_option('mandir')
foreach man_page : ['cloud-init.1', 'cloud-id.1', 'cloud-init-per.1']
  install_data(
    'doc/man/' + man_page,
    install_dir: join_paths(mandir,  'man1'),
    install_tag: 'docs'
  )
endforeach

# Prerequisite for using install_deps or install_test_deps:
# python3 -m venv venv
# source ./venv/bin/activate
# meson setup builddir
# meson -C builddir compile install_deps
run_target(
  'install_deps',
  command: [python, '-m', 'pip', 'install', '-r', 'requirements.txt'],
)
run_target(
  'install_test_deps',
  command: [python, '-m', 'pip', 'install', '-r', meson.project_source_root() / 'test-requirements.txt'],
)

# CLI: meson compile -C buildir py3
test(
  'py3',
  python,
  args: ['-m', 'pytest', meson.project_source_root() / 'tests' / 'unittests'],
  timeout: 180,
  is_parallel: true
)
