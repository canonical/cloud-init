try:
    from hypothesis_jsonschema import from_schema

    HAS_HYPOTHESIS_JSONSCHEMA = True
except ImportError:
    HAS_HYPOTHESIS_JSONSCHEMA = False

    def from_schema(*_, **__):  # type: ignore
        pass


__all__ = ["from_schema", "HAS_HYPOTHESIS_JSONSCHEMA"]
