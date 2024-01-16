from pathlib import Path

import cloudinit


def get_top_level_dir() -> Path:
    """Return the absolute path to the top cloudinit project directory

    @return Path('<top-cloudinit-dir>')
    """
    return Path(cloudinit.__file__).parent.parent.resolve()


def cloud_init_project_dir(sub_path: str) -> str:
    """Get a path within the cloudinit project directory

    @return str of the combined path

    Example: cloud_init_project_dir("my/path") -> "/path/to/cloud-init/my/path"
    """
    return str(get_top_level_dir() / sub_path)
