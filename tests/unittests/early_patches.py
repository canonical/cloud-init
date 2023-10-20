import functools
from typing import Callable

old_lru_cache = functools.lru_cache
cached_functions = []


def wrapped_lru_cache(*args, **kwargs):
    def wrapper(func: Callable, *a, **k):
        new_func = old_lru_cache(*args, **kwargs)(func, *a, **k)

        # Without this check, we'll also store stdlib functions with @lru_cache
        if "cloudinit" in func.__module__:
            # Imports only happen once, so we don't need to worry about
            # duplicates here
            cached_functions.append(new_func)
        return new_func

    return wrapper


def get_cached_functions():
    return cached_functions


functools.lru_cache = wrapped_lru_cache
