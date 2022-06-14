import os

from tests.hypothesis import HAS_HYPOTHESIS

if HAS_HYPOTHESIS:
    from hypothesis import Verbosity, settings

    _hypothesis_profiles = {
        "ci": {"max_examples": 100},
        "debug": {"max_examples": 10, "verbosity": Verbosity.verbose},
    }
    for name, kwargs in _hypothesis_profiles.items():
        settings.register_profile(name, parent=None, **kwargs)
    settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "default"))
