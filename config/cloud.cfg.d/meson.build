#https://mesonbuild.com/FAQ.html#but-i-really-want-to-use-wildcards
c = run_command(find, '-name', '*.cfg', check: true)
install_data(
  c.stdout().strip().split('\n'),
  install_dir: join_paths(sysconfdir, 'cloud', 'cloud.cfg.d'),
  install_tag: 'config'
)
install_data(
  ['README'],
  install_dir: join_paths(sysconfdir, 'cloud', 'cloud.cfg.d'),
  install_tag: 'config'
)
