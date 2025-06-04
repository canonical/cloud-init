#https://mesonbuild.com/FAQ.html#but-i-really-want-to-use-wildcards
c = run_command(find, '-name', '*.txt', check: true)
install_data(
  c.stdout().strip().split('\n'),
  install_dir: join_paths(
    get_option('datadir'), 'doc', 'cloud-init', 'examples'
  ),
  install_tag: 'docs'
)
