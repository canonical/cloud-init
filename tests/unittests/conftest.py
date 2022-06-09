import os

from hypothesis import Verbosity, settings

_hypothesis_profiles = {
    "ci": {"max_examples": 100},
    "debug": {"max_examples": 10, "verbosity": Verbosity.verbose},
}
try:
    for name, kwargs in _hypothesis_profiles.items():
        settings.register_profile(name, **kwargs)
except TypeError:
    # Drop except when hypothesis>=3.47
    # https://hypothesis.readthedocs.io/en/latest/changes.html#v3-47-0
    for name, kwargs in _hypothesis_profiles.items():
        settings.register_profile(name, settings(**kwargs))
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "default"))
