from pathlib import Path

# With the single process optimization, cloud-init-main.service runs every
# stage and the per-stage services are shims that only signal it over a
# socket. Where the optimization is patched out, each stage service runs
# cloud-init itself and the network stage may still be cloud-init.service.
# Wrap whichever of these services actually execute cloud-init.
services = [
    "cloud-init-main.service",
    "cloud-init-local.service",
    "cloud-init-network.service",
    "cloud-init.service",
    "cloud-config.service",
    "cloud-final.service",
]
service_dir = Path("/lib/systemd/system/")

# Prepend the ExecStart= line with 'python3 -m coverage run'
patched = False
for service in services:
    file_path = service_dir / service
    if not file_path.is_file():
        continue
    content = file_path.read_text()
    if "ExecStart=/usr" not in content:
        continue
    content = content.replace(
        "ExecStart=/usr",
        (
            "ExecStart=python3 -m coverage run "
            "--source=/usr/lib/python3/dist-packages/cloudinit --append /usr"
        ),
    )
    file_path.write_text(content)
    patched = True

if not patched:
    print(f"Error: no service in {service_dir} runs cloud-init from /usr")
    exit(1)
