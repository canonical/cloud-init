
install_data(
  'disable-sshd-keygen-if-cloud-init-active.conf',
  install_dir: join_paths(systemd_unit_dir, 'sshd-keygen@.service.d'),
  install_tag: 'systemd'
)

# Allow for simple fork-related drop-ins in other downstreams
# https://mesonbuild.com/FAQ.html#but-i-really-want-to-use-wildcards
services = run_command(find, '-name', '*.service', check: true).stdout().strip()
targets = run_command(find, '-name', '*.target', check: true).stdout().strip()
sockets = run_command(find, '-name', '*.socket', check: true).stdout().strip()
install_data(
  services.split('\n') + targets.split('\n') + sockets.split('\n'),
  install_dir: systemd_unit_dir,
  install_tag: 'systemd'
)
