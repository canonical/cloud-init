#https://mesonbuild.com/FAQ.html#but-i-really-want-to-use-wildcards
c = run_command(find, '-name', '*.tmpl', check: true)
install_data(
  c.stdout().strip().split('\n'),
  install_dir: join_paths(sysconfdir, 'cloud', 'templates'),
  install_tag: 'config'
)
