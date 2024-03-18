from pathlib import Path

services = [
    "cloud-init-local.service",
    "cloud-init.service",
    "cloud-config.service",
    "cloud-final.service",
]
service_dir = Path("/lib/systemd/system/")

# Check for the existence of the service files
for service in services:
    if not (service_dir / service).is_file():
        print(f"Error: {service} does not exist in {service_dir}")
        exit(1)

# Prepend the ExecStart= line with 'python3 -m coverage run'
for service in services:
    file_path = service_dir / service
    content = file_path.read_text()
    content = content.replace(
        "ExecStart=/usr",
        (
            "ExecStart=python3 -m coverage run "
            "--source=/usr/lib/python3/dist-packages/cloudinit --append /usr"
        ),
    )
    file_path.write_text(content)
