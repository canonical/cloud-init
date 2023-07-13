import functools

old_lru_cache = functools.lru_cache
cached_functions = []


def wrapped_lru_cache(*args, **kwargs):
    def wrapper(func):
        new_func = old_lru_cache(*args, **kwargs)(func)
        cached_functions.append(new_func)
        return new_func

    return wrapper


def get_cached_functions():
    return cached_functions


functools.lru_cache = wrapped_lru_cache
