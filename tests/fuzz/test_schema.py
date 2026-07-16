import os
from copy import deepcopy
from typing import Optional, Sequence, Set

from hypothesis import given, settings
from hypothesis_jsonschema import from_schema

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)

settings.register_profile("ci", max_examples=1000)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "default"))


def remove_modules(schema, modules: Set[str]) -> dict:
    indices_to_delete = set()
    for module in set(modules):
        for index, ref_dict in enumerate(schema["allOf"]):
            if ref_dict["$ref"] == f"#/$defs/{module}":
                indices_to_delete.add(index)
                continue  # module found
    for index in indices_to_delete:
        schema["allOf"].pop(index)
    return schema


def remove_defs(schema, defs: Set[str]) -> dict:
    defs_to_delete = set(schema["$defs"].keys()).intersection(set(defs))
    for key in defs_to_delete:
        del schema["$defs"][key]
    return schema


def clean_schema(
    schema=None,
    modules: Optional[Sequence[str]] = None,
    defs: Optional[Sequence[str]] = None,
):
    schema = deepcopy(schema or get_schema())
    if modules:
        remove_modules(schema, set(modules))
    if defs:
        remove_defs(schema, set(defs))
    del schema["properties"]
    del schema["additionalProperties"]
    return schema


class TestSchemaFuzz:
    # Avoid https://github.com/Zac-HD/hypothesis-jsonschema/issues/97
    SCHEMA = clean_schema(
        modules=["cc_users_groups"],
        defs=["users_groups.groups_by_groupname", "users_groups.user"],
    )

    @given(from_schema(SCHEMA))
    def test_validate_full_schema(self, orig_config):
        config = deepcopy(orig_config)
        valid_props = get_schema()["properties"].keys()
        for key in orig_config.keys():
            if key not in valid_props:
                del config[key]
        try:
            validate_cloudconfig_schema(config, strict=True)
        except SchemaValidationError as ex:
            if ex.has_errors():
                raise
