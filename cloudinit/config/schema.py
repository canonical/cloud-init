# This file is part of cloud-init. See LICENSE file for license information.
"""schema.py: Set of module functions for processing cloud-config schema."""
import argparse
import glob
import json
import logging
import os
import re
import shutil
import sys
import textwrap
from collections import defaultdict
from collections.abc import Iterable
from contextlib import suppress
from copy import deepcopy
from enum import Enum
from errno import EACCES
from functools import partial
from itertools import chain
from typing import (
    TYPE_CHECKING,
    DefaultDict,
    List,
    NamedTuple,
    Optional,
    Tuple,
    Type,
    Union,
    cast,
)

import yaml

from cloudinit import features, importer, safeyaml
from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.handlers import INCLUSION_TYPES_MAP, type_from_starts_with
from cloudinit.helpers import Paths
from cloudinit.sources import DataSourceNotFoundException
from cloudinit.temp_utils import mkdtemp
from cloudinit.util import (
    error,
    get_modules_from_dir,
    load_text_file,
    load_yaml,
    should_log_deprecation,
    write_file,
)

try:
    from jsonschema import ValidationError as _ValidationError

    ValidationError = _ValidationError
except ImportError:
    ValidationError = Exception  # type: ignore


LOG = logging.getLogger(__name__)


# Note versions.schema.json is publicly consumed by schemastore.org.
# If we change the location of versions.schema.json in github, we need
# to provide an updated PR to
# https://github.com/SchemaStore/schemastore.
VERSIONED_USERDATA_SCHEMA_FILE = "versions.schema.cloud-config.json"

# When bumping schema version due to incompatible changes:
# 1. Add a new schema-cloud-config-v#.json
# 2. change the USERDATA_SCHEMA_FILE to cloud-init-schema-v#.json
# 3. Add the new version definition to versions.schema.cloud-config.json
USERDATA_SCHEMA_FILE = "schema-cloud-config-v1.json"
NETWORK_CONFIG_V1_SCHEMA_FILE = "schema-network-config-v1.json"
NETWORK_CONFIG_V2_SCHEMA_FILE = "schema-network-config-v2.json"

_YAML_MAP = {True: "true", False: "false", None: "null"}
SCHEMA_DOC_TMPL = """
{name}
{title_underbar}

{title}

.. tab-set::

{prefix3}.. tab-item:: Summary

{description}

{prefix6}**Internal name:** ``{id}``

{prefix6}**Module frequency:** {frequency}

{prefix6}**Supported distros:** {distros}

{prefix6}{activate_by_schema_keys}

{prefix3}.. tab-item:: Config schema

{property_doc}

{prefix3}.. tab-item:: Examples

{prefix6}::

{examples}
"""
SCHEMA_PROPERTY_TMPL = "{prefix}* **{prop_name}:** ({prop_type}){description}"
SCHEMA_LIST_ITEM_TMPL = (
    "{prefix}* Each object in **{prop_name}** list supports "
    "the following keys:"
)
DEPRECATED_KEY = "deprecated"

# user-data files typically must begin with a leading '#'
USERDATA_VALID_HEADERS = sorted(
    [t for t in INCLUSION_TYPES_MAP.keys() if t[0] == "#"]
)

# type-annotate only if type-checking.
# Consider to add `type_extensions` as a dependency when Bionic is EOL.
if TYPE_CHECKING:
    import typing

    from typing_extensions import NotRequired, TypedDict

    class MetaSchema(TypedDict):
        id: str
        name: str
        title: str
        description: str
        distros: typing.List[str]
        examples: typing.List[Union[dict, str]]
        frequency: str
        activate_by_schema_keys: NotRequired[List[str]]

else:
    MetaSchema = dict


class SchemaDeprecationError(ValidationError):
    def __init__(
        self,
        message: str,
        version: str,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.version: str = version


class SchemaProblem(NamedTuple):
    path: str
    message: str

    def format(self) -> str:
        return f"{self.path}: {self.message}"


SchemaProblems = List[SchemaProblem]


class SchemaType(Enum):
    """Supported schema types are either cloud-config or network-config.

    Vendordata and Vendordata2 format adheres to cloud-config schema type.
    Cloud Metadata is unique schema to each cloud platform and likely will not
    be represented in this enum.
    """

    CLOUD_CONFIG = "cloud-config"
    NETWORK_CONFIG = "network-config"
    NETWORK_CONFIG_V1 = "network-config-v1"
    NETWORK_CONFIG_V2 = "network-config-v2"


# Placeholders for versioned schema and schema file locations.
# The "latest" key is used in absence of a requested specific version.
SCHEMA_FILES_BY_TYPE = {
    SchemaType.CLOUD_CONFIG: {
        "latest": USERDATA_SCHEMA_FILE,
    },
    SchemaType.NETWORK_CONFIG: {
        "latest": NETWORK_CONFIG_V2_SCHEMA_FILE,
    },
    SchemaType.NETWORK_CONFIG_V1: {
        "latest": NETWORK_CONFIG_V1_SCHEMA_FILE,
    },
    SchemaType.NETWORK_CONFIG_V2: {
        "latest": NETWORK_CONFIG_V2_SCHEMA_FILE,
    },
}


class InstanceDataType(Enum):
    """Types of instance data provided to cloud-init"""

    USERDATA = "user-data"
    NETWORK_CONFIG = "network-config"
    VENDORDATA = "vendor-data"
    VENDOR2DATA = "vendor2-data"
    # METADATA = "metadata"

    def __str__(self):  # pylint: disable=invalid-str-returned
        return self.value


class InstanceDataPart(NamedTuple):
    config_type: InstanceDataType
    schema_type: SchemaType
    config_path: str


class UserDataTypeAndDecodedContent(NamedTuple):
    userdata_type: str
    content: str


def _format_schema_problems(
    schema_problems: SchemaProblems,
    *,
    prefix: Optional[str] = None,
    separator: str = ", ",
) -> str:
    formatted = separator.join(map(lambda p: p.format(), schema_problems))
    if prefix:
        formatted = f"{prefix}{formatted}"
    return formatted


class SchemaValidationError(ValueError):
    """Raised when validating a cloud-config file against a schema."""

    def __init__(
        self,
        schema_errors: Optional[SchemaProblems] = None,
        schema_deprecations: Optional[SchemaProblems] = None,
    ):
        """Init the exception an n-tuple of schema errors.

        @param schema_errors: An n-tuple of the format:
            ((flat.config.key, msg),)
        @param schema_deprecations: An n-tuple of the format:
            ((flat.config.key, msg),)
        """
        message = ""

        def handle_problems(problems, prefix):
            if not problems:
                return problems
            nonlocal message
            if message:
                message += "\n\n"
            problems = sorted(list(set(problems)))
            message += _format_schema_problems(problems, prefix=prefix)
            return problems

        self.schema_errors = handle_problems(
            schema_errors,
            prefix="Cloud config schema errors: ",
        )
        self.schema_deprecations = handle_problems(
            schema_deprecations,
            prefix="Cloud config schema deprecations: ",
        )
        super().__init__(message)

    def has_errors(self) -> bool:
        return bool(self.schema_errors)


class SchemaValidationInvalidHeaderError(SchemaValidationError):
    """Raised when no valid header is declared in the user-data file."""


def is_schema_byte_string(checker, instance):
    """TYPE_CHECKER override allowing bytes for string type

    For jsonschema v. 3.0.0+
    """
    try:
        from jsonschema import Draft4Validator
    except ImportError:
        return False
    return Draft4Validator.TYPE_CHECKER.is_type(
        instance, "string"
    ) or isinstance(instance, (bytes,))


def _add_deprecated_changed_or_new_msg(
    config: dict, annotate=False, filter_key=None
) -> str:
    """combine description with new/changed/deprecated message

    deprecated/changed/new keys require a _version key (this is verified
    in a unittest), a _description key is optional
    """

    def format_message(key: str):
        if not config.get(f"{key}"):
            return ""
        key_description = config.get(f"{key}_description", "")
        v = config.get(
            f"{key}_version",
            f"<missing {key}_version key, please file a bug report>",
        )
        msg = f"{key.capitalize()} in version {v}. {key_description}"
        if annotate:
            return f" {msg}"

        # italicised RST - no whitespace between astrisk and text
        return f"\n\n*{msg.strip()}*"

    # define print order
    filter_keys = (
        filter_key if filter_key else ["deprecated", "changed", "new"]
    )

    # build a deprecation/new/changed string
    changed_new_deprecated = "".join(map(format_message, filter_keys))
    description = config.get("description", "")
    return f"{description}{changed_new_deprecated}".rstrip()


def cloud_init_deepest_matches(errors, instance) -> List[ValidationError]:
    """Return the best_match errors based on the deepest match in the json_path

    This is useful for anyOf and oneOf subschemas where the most-specific error
    tends to be the most appropriate.
    """
    best_matches = []
    path_depth = 0
    is_type = isinstance(instance, dict) and "type" in instance
    for err in errors:
        if is_type:
            # Most appropriate subschema matches given type
            if instance["type"] in err.schema.get("properties", {}).get(
                "type", {}
            ).get("enum", []):
                return [err]

            if hasattr(err, "json_path"):
                if err.json_path[-4:] == "type":
                    # Prioritize cloud-init 'type'-related errors exclusively
                    best_matches.append(err)
            elif err.path and err.path[0] == "type":
                # Use err.paths instead of json_path on jsonschema <= 3.2
                # Prioritize cloud-init 'type'-related errors exclusively
                best_matches.append(err)
        elif len(err.path) == path_depth:
            best_matches.append(err)
        elif len(err.path) > path_depth:
            path_depth = len(err.path)
            best_matches = [err]
    return best_matches


def _validator(
    _validator,
    deprecated: bool,
    _instance,
    schema: dict,
    filter_key: str,
    error_type: Type[Exception] = SchemaDeprecationError,
):
    """Jsonschema validator for `deprecated` items.

    It yields an instance of `error_type` if deprecated that must be handled,
    otherwise the instance is consider faulty.
    """
    if deprecated:
        msg = _add_deprecated_changed_or_new_msg(
            schema, annotate=True, filter_key=[filter_key]
        )
        yield error_type(msg, schema.get("deprecated_version", "devel"))


_validator_deprecated = partial(_validator, filter_key="deprecated")
_validator_changed = partial(_validator, filter_key="changed")


def _anyOf(
    validator,
    anyOf,
    instance,
    _schema,
    error_type: Type[Exception] = SchemaDeprecationError,
):
    """Jsonschema validator for `anyOf`.

    It treats occurrences of `error_type` as non-errors, but yield them for
    external processing. Useful to process schema annotations, as `deprecated`.

    Cloud-init's network schema under the `config` key has a complexity of
    allowing each list dict item to declare it's type with a `type` key which
    can contain the values: bond, bridge, nameserver, physical, route, vlan.

    This schema 'flexibility' makes it hard for the default
    jsonschema.exceptions.best_match function to find the correct schema
    failure because it typically returns the failing schema error based on
    the schema of greatest match depth. Since each anyOf dict matches the
    same depth into the network schema path, `best_match` just returns the
    first set of schema errors, which is almost always incorrect.

    To find a better schema match when encountering schema validation errors,
    cloud-init network schema introduced schema $defs with the prefix
    `anyOf_type_`. If the object we are validating contains a 'type' key, and
    one of the failing schema objects in an anyOf clause has a name of the
    format anyOf_type_XXX, raise those schema errors instead of calling
    best_match.
    """
    from jsonschema.exceptions import best_match

    all_errors = []
    all_deprecations = []
    skip_best_match = False
    for index, subschema in enumerate(anyOf):
        all_errs = list(
            validator.descend(instance, subschema, schema_path=index)
        )
        errs = list(filter(lambda e: not isinstance(e, error_type), all_errs))
        deprecations = list(
            filter(lambda e: isinstance(e, error_type), all_errs)
        )
        if not errs:
            all_deprecations.extend(deprecations)
            break
        if (
            isinstance(instance, dict)
            and "type" in instance
            and "anyOf_type" in subschema.get("$ref", "")
        ):
            if f"anyOf_type_{instance['type']}" in subschema["$ref"]:
                # A matching anyOf_type_XXX $ref indicates this is likely the
                # best_match ValidationError. Skip best_match below.
                skip_best_match = True
                yield from errs
        all_errors.extend(errs)
    else:
        if not skip_best_match:
            yield best_match(all_errors)
        yield ValidationError(
            "%r is not valid under any of the given schemas" % (instance,),
            context=all_errors,
        )
    yield from all_deprecations


def _oneOf(
    validator,
    oneOf,
    instance,
    _schema,
    error_type: Type[Exception] = SchemaDeprecationError,
):
    """Jsonschema validator for `oneOf`.

    It treats occurrences of `error_type` as non-errors, but yield them for
    external processing. Useful to process schema annotations, as `deprecated`.
    """
    subschemas = enumerate(oneOf)
    all_errors = []
    all_deprecations = []
    for index, subschema in subschemas:
        all_errs = list(
            validator.descend(instance, subschema, schema_path=index)
        )
        errs = list(filter(lambda e: not isinstance(e, error_type), all_errs))
        deprecations = list(
            filter(lambda e: isinstance(e, error_type), all_errs)
        )
        if not errs:
            first_valid = subschema
            all_deprecations.extend(deprecations)
            break
        all_errors.extend(errs)
    else:
        yield from cloud_init_deepest_matches(all_errors, instance)

    more_valid = [s for i, s in subschemas if validator.is_valid(instance, s)]
    if more_valid:
        more_valid.append(first_valid)
        reprs = ", ".join(repr(schema) for schema in more_valid)
        yield ValidationError(
            "%r is valid under each of %s" % (instance, reprs)
        )
    else:
        yield from all_deprecations


def get_jsonschema_validator():
    """Get metaschema validator and format checker

    Older versions of jsonschema require some compatibility changes.

    @returns: Tuple: (jsonschema.Validator, FormatChecker)
    @raises: ImportError when jsonschema is not present
    """
    from jsonschema import Draft4Validator, FormatChecker
    from jsonschema.validators import create

    # Allow for bytes to be presented as an acceptable valid value for string
    # type jsonschema attributes in cloud-init's schema.
    # This allows #cloud-config to provide valid yaml "content: !!binary | ..."

    meta_schema = deepcopy(Draft4Validator.META_SCHEMA)

    # This additional label allows us to specify a different name
    # than the property key when generating docs.
    # This is especially useful when using a "patternProperties" regex,
    # otherwise the property label in the generated docs will be a
    # regular expression.
    # http://json-schema.org/understanding-json-schema/reference/object.html#pattern-properties
    meta_schema["properties"]["label"] = {"type": "string"}

    validator_kwargs = {}
    if hasattr(Draft4Validator, "TYPE_CHECKER"):  # jsonschema 3.0+
        meta_schema["additionalProperties"] = False  # Unsupported in 2.6.0
        type_checker = Draft4Validator.TYPE_CHECKER.redefine(
            "string", is_schema_byte_string
        )
        validator_kwargs = {
            "type_checker": type_checker,
        }
    else:  # jsonschema 2.6 workaround
        # pylint:disable-next=no-member
        types = Draft4Validator.DEFAULT_TYPES  # pylint: disable=E1101
        # Allow bytes as well as string (and disable a spurious unsupported
        # assignment-operation pylint warning which appears because this
        # code path isn't written against the latest jsonschema).
        types["string"] = (str, bytes)  # pylint: disable=E1137
        validator_kwargs = {"default_types": types}

    # Add deprecation handling
    validators = dict(Draft4Validator.VALIDATORS)
    validators[DEPRECATED_KEY] = _validator_deprecated
    validators["changed"] = _validator_changed
    validators["oneOf"] = _oneOf
    validators["anyOf"] = _anyOf

    cloudinitValidator = create(
        meta_schema=meta_schema,
        validators=validators,
        version="draft4",
        **validator_kwargs,
    )

    # Add deprecation handling
    def is_valid(self, instance, _schema=None, **__):
        """Override version of `is_valid`.

        It does ignore instances of `SchemaDeprecationError`.
        """
        errors = filter(
            lambda e: not isinstance(  # pylint: disable=W1116
                e, SchemaDeprecationError
            ),
            self.iter_errors(instance, _schema),
        )
        return next(errors, None) is None

    cloudinitValidator.is_valid = is_valid

    return (cloudinitValidator, FormatChecker)


def validate_cloudconfig_metaschema(validator, schema: dict, throw=True):
    """Validate provided schema meets the metaschema definition. Return strict
    Validator and FormatChecker for use in validation
    @param validator: Draft4Validator instance used to validate the schema
    @param schema: schema to validate
    @param throw: Sometimes the validator and checker are required, even if
        the schema is invalid. Toggle for whether to raise
        SchemaValidationError or log warnings.

    @raises: ImportError when jsonschema is not present
    @raises: SchemaValidationError when the schema is invalid
    """

    from jsonschema.exceptions import SchemaError

    try:
        validator.check_schema(schema)
    except SchemaError as err:
        # Raise SchemaValidationError to avoid jsonschema imports at call
        # sites
        if throw:
            raise SchemaValidationError(
                schema_errors=[
                    SchemaProblem(
                        ".".join([str(p) for p in err.path]), err.message
                    )
                ]
            ) from err
        LOG.warning(
            "Meta-schema validation failed, attempting to validate config "
            "anyway: %s",
            err,
        )


def network_schema_version(network_config: dict) -> Optional[int]:
    """Return the version of the network schema when present."""
    if "network" in network_config:
        return network_config["network"].get("version")
    return network_config.get("version")


def netplan_validate_network_schema(
    network_config: dict,
    strict: bool = False,
    annotate: bool = False,
    log_details: bool = True,
) -> bool:
    """On systems with netplan, validate network_config schema for file

    Leverage NetplanParser for error annotation line, column and detailed
    errors.

    @param network_config: Dict of network configuration settings validated
        against
    @param strict: Boolean, when True raise SchemaValidationErrors instead of
       logging warnings.
    @param annotate: Boolean, when True, print original network_config_file
        content with error annotations
    @param log_details: Boolean, when True logs details of validation errors.
       If there are concerns about logging sensitive userdata, this should
       be set to False.

    @return: True when schema validation was performed. False when not on a
        system with netplan and netplan python support.
    @raises: SchemaValidationError when netplan's parser raises
        NetplanParserExceptions.
    """
    try:
        from netplan import NetplanParserException, Parser  # type: ignore
    except ImportError:
        LOG.debug(
            "Skipping netplan schema validation. No netplan API available"
        )
        return False

    # netplan Parser looks at all *.yaml files in the target directory underA
    # /etc/netplan. cloud-init should only validate schema of the
    # network-config it generates, so create a <tmp_dir>/etc/netplan
    # to validate only our network-config.
    parse_dir = mkdtemp()
    netplan_file = os.path.join(parse_dir, "etc/netplan/network-config.yaml")

    # Datasource network config can optionally exclude top-level network key
    net_cfg = deepcopy(network_config)
    if "network" not in net_cfg:
        net_cfg = {"network": net_cfg}

    src_content = safeyaml.dumps(net_cfg)
    write_file(netplan_file, src_content, mode=0o600)

    parser = Parser()
    errors = []
    try:
        # Parse all netplan *.yaml files.load_yaml_hierarchy looks for nested
        # etc/netplan subdir under "/".
        parser.load_yaml_hierarchy(parse_dir)
    except NetplanParserException as e:
        errors.append(
            SchemaProblem(
                "format-l{line}.c{col}".format(line=e.line, col=e.column),
                f"Invalid netplan schema. {e.message}",
            )
        )
    if os.path.exists(parse_dir):
        shutil.rmtree(parse_dir)
    if errors:
        if strict:
            if annotate:
                # Load YAML marks for annotation
                _, marks = safeyaml.load_with_marks(src_content)
                print(
                    annotated_cloudconfig_file(
                        net_cfg,
                        src_content,
                        marks,
                        schema_errors=errors,
                    )
                )
            raise SchemaValidationError(errors)
        if log_details:
            message = _format_schema_problems(
                errors,
                prefix=(
                    f"{SchemaType.NETWORK_CONFIG.value} failed "
                    "schema validation!\n"
                ),
                separator="\n",
            )
        else:
            message = (
                f"{SchemaType.NETWORK_CONFIG.value} failed schema validation! "
                "You may run 'sudo cloud-init schema --system' to "
                "check the details."
            )
        LOG.warning(message)
    return True


def validate_cloudconfig_schema(
    config: dict,
    schema: Optional[dict] = None,
    schema_type: SchemaType = SchemaType.CLOUD_CONFIG,
    strict: bool = False,
    strict_metaschema: bool = False,
    log_details: bool = True,
    log_deprecations: bool = False,
) -> bool:
    """Validate provided config meets the schema definition.

    @param config: Dict of cloud configuration settings validated against
        schema. Ignored if strict_metaschema=True
    @param schema: jsonschema dict describing the supported schema definition
       for the cloud config module (config.cc_*). If None, validate against
       global schema.
    @param schema_type: Optional SchemaType.
       One of: SchemaType.CLOUD_CONFIG or SchemaType.NETWORK_CONFIG_V1 or
            SchemaType.NETWORK_CONFIG_V2
       Default: SchemaType.CLOUD_CONFIG
    @param strict: Boolean, when True raise SchemaValidationErrors instead of
       logging warnings.
    @param strict_metaschema: Boolean, when True validates schema using strict
       metaschema definition at runtime (currently unused)
    @param log_details: Boolean, when True logs details of validation errors.
       If there are concerns about logging sensitive userdata, this should
       be set to False.
    @param log_deprecations: Controls whether to log deprecations or not.

    @raises: SchemaValidationError when provided config does not validate
        against the provided schema.
    @raises: RuntimeError when provided config sourced from YAML is not a dict.
    @raises: ValueError on invalid schema_type not in CLOUD_CONFIG or
        NETWORK_CONFIG_V1 or NETWORK_CONFIG_V2
    """
    from cloudinit.net.netplan import available as netplan_available

    if schema_type == SchemaType.NETWORK_CONFIG:
        network_version = network_schema_version(config)
        if network_version == 2:
            schema_type = SchemaType.NETWORK_CONFIG_V2
        elif network_version == 1:
            schema_type = SchemaType.NETWORK_CONFIG_V1
        schema = get_schema(schema_type)

    if schema_type == SchemaType.NETWORK_CONFIG_V2:
        if netplan_validate_network_schema(
            network_config=config, strict=strict, log_details=log_details
        ):
            # Schema was validated by netplan
            return True
        elif netplan_available():
            # We found no netplan API on netplan system, do not perform schema
            # validation against cloud-init's network v2 schema because netplan
            # supports more config keys than in cloud-init's netv2 schema.
            # This may result in schema warnings for valid netplan config
            # which would be successfully rendered by netplan but doesn't
            # adhere to cloud-init's network v2.
            return False

    if schema is None:
        schema = get_schema(schema_type)
    try:
        (cloudinitValidator, FormatChecker) = get_jsonschema_validator()
        if strict_metaschema:
            validate_cloudconfig_metaschema(
                cloudinitValidator, schema, throw=False
            )
    except ImportError:
        LOG.debug("Ignoring schema validation. jsonschema is not present")
        return False

    validator = cloudinitValidator(schema, format_checker=FormatChecker())

    errors: SchemaProblems = []
    deprecations: SchemaProblems = []
    info_deprecations: SchemaProblems = []
    for schema_error in sorted(
        validator.iter_errors(config), key=lambda e: e.path
    ):
        path = ".".join([str(p) for p in schema_error.path])
        if (
            not path
            and schema_error.validator == "additionalProperties"
            and schema_error.schema == schema
        ):
            # an issue with invalid top-level property
            prop_match = re.match(
                r".*\('(?P<name>.*)' was unexpected\)", schema_error.message
            )
            if prop_match:
                path = prop_match["name"]
        if isinstance(
            schema_error, SchemaDeprecationError
        ):  # pylint: disable=W1116
            if schema_error.version == "devel" or should_log_deprecation(
                schema_error.version, features.DEPRECATION_INFO_BOUNDARY
            ):
                deprecations.append(SchemaProblem(path, schema_error.message))
            else:
                info_deprecations.append(
                    SchemaProblem(path, schema_error.message)
                )
        else:
            errors.append(SchemaProblem(path, schema_error.message))

    if log_deprecations:
        if info_deprecations:
            message = _format_schema_problems(
                info_deprecations,
                prefix="Deprecated cloud-config provided: ",
            )
            LOG.info(message)
        if deprecations:
            message = _format_schema_problems(
                deprecations,
                prefix="Deprecated cloud-config provided: ",
            )
            # This warning doesn't fit the standardized util.deprecated()
            # utility format, but it is a deprecation log, so log it directly.
            LOG.deprecated(message)  # type: ignore
    if strict and (errors or deprecations or info_deprecations):
        raise SchemaValidationError(errors, deprecations + info_deprecations)
    if errors:
        if log_details:
            details = _format_schema_problems(
                errors,
                prefix=f"{schema_type.value} failed schema validation!\n",
                separator="\n",
            )
        else:
            details = (
                f"{schema_type.value} failed schema validation! "
                "You may run 'sudo cloud-init schema --system' to "
                "check the details."
            )
        LOG.warning(details)
    return True


class _Annotator:
    def __init__(
        self,
        cloudconfig: dict,
        original_content: str,
        schemamarks: dict,
    ):
        self._cloudconfig = cloudconfig
        self._original_content = original_content
        self._schemamarks = schemamarks

    @staticmethod
    def _build_footer(title: str, content: List[str]) -> str:
        body = "\n".join(content)
        return f"# {title}: -------------\n{body}\n\n"

    def _build_errors_by_line(self, schema_problems: SchemaProblems):
        errors_by_line: DefaultDict[Union[str, int], List] = defaultdict(list)
        for path, msg in schema_problems:
            match = re.match(r"format-l(?P<line>\d+)\.c(?P<col>\d+).*", path)
            if match:
                line, col = match.groups()
                errors_by_line[int(line)].append(msg)
            else:
                col = None
                errors_by_line[self._schemamarks[path]].append(msg)
            if col is not None:
                msg = "Line {line} column {col}: {msg}".format(
                    line=line, col=col, msg=msg
                )
        return errors_by_line

    @staticmethod
    def _add_problems(
        problems: List[str],
        labels: List[str],
        footer: List[str],
        index: int,
        label_prefix: str = "",
    ) -> int:
        for problem in problems:
            label = f"{label_prefix}{index}"
            labels.append(label)
            footer.append(f"# {label}: {problem}")
            index += 1
        return index

    def _annotate_content(
        self,
        lines: List[str],
        errors_by_line: dict,
        deprecations_by_line: dict,
    ) -> List[str]:
        annotated_content = []
        error_footer: List[str] = []
        deprecation_footer: List[str] = []
        error_index = 1
        deprecation_index = 1
        for line_number, line in enumerate(lines, 1):
            errors = errors_by_line[line_number]
            deprecations = deprecations_by_line[line_number]
            if errors or deprecations:
                labels: List[str] = []
                error_index = self._add_problems(
                    errors, labels, error_footer, error_index, label_prefix="E"
                )
                deprecation_index = self._add_problems(
                    deprecations,
                    labels,
                    deprecation_footer,
                    deprecation_index,
                    label_prefix="D",
                )
                annotated_content.append(line + "\t\t# " + ",".join(labels))
            else:
                annotated_content.append(line)

        annotated_content.extend(
            map(
                lambda seq: self._build_footer(*seq),
                filter(
                    lambda seq: bool(seq[1]),
                    (
                        ("Errors", error_footer),
                        ("Deprecations", deprecation_footer),
                    ),
                ),
            )
        )
        return annotated_content

    def annotate(
        self,
        schema_errors: SchemaProblems,
        schema_deprecations: SchemaProblems,
    ) -> str:
        if not schema_errors and not schema_deprecations:
            return self._original_content
        lines = self._original_content.split("\n")
        errors_by_line = self._build_errors_by_line(schema_errors)
        deprecations_by_line = self._build_errors_by_line(schema_deprecations)
        annotated_content = self._annotate_content(
            lines, errors_by_line, deprecations_by_line
        )
        return "\n".join(annotated_content)


def annotated_cloudconfig_file(
    cloudconfig: dict,
    original_content: str,
    schemamarks: dict,
    *,
    schema_errors: Optional[SchemaProblems] = None,
    schema_deprecations: Optional[SchemaProblems] = None,
) -> Union[str, bytes]:
    """Return contents of the cloud-config file annotated with schema errors.

    @param cloudconfig: YAML-loaded dict from the original_content or empty
        dict if unparsable.
    @param original_content: The contents of a cloud-config file
    @param schemamarks: Dict with schema marks.
    @param schema_errors: Instance of `SchemaProblems`.
    @param schema_deprecations: Instance of `SchemaProblems`.

    @return Annotated schema
    """
    return _Annotator(cloudconfig, original_content, schemamarks).annotate(
        schema_errors or [], schema_deprecations or []
    )


def process_merged_cloud_config_part_problems(
    content: str,
) -> List[SchemaProblem]:
    """Annotate and return schema validation errors in merged cloud-config.txt

    When merging multiple cloud-config parts cloud-init logs an error and
    ignores any user-data parts which are declared as #cloud-config but
    cannot be processed. the handler.cloud_config module also leaves comments
    in the final merged config for every invalid part file which begin with
    MERGED_CONFIG_SCHEMA_ERROR_PREFIX to aid in triage.
    """
    from cloudinit.handlers.cloud_config import MERGED_PART_SCHEMA_ERROR_PREFIX

    if MERGED_PART_SCHEMA_ERROR_PREFIX not in content:
        return []
    errors: List[SchemaProblem] = []
    for line_num, line in enumerate(content.splitlines(), 1):
        if line.startswith(MERGED_PART_SCHEMA_ERROR_PREFIX):
            errors.append(
                SchemaProblem(
                    f"format-l{line_num}.c1",
                    line.replace(
                        MERGED_PART_SCHEMA_ERROR_PREFIX,
                        "Ignored invalid user-data: ",
                    ),
                )
            )
    return errors


def _get_config_type_and_rendered_userdata(
    config_path: str,
    content: str,
    instance_data_path: Optional[str] = None,
) -> UserDataTypeAndDecodedContent:
    """
    Return tuple of user-data-type and rendered content.

    When encountering jinja user-data, render said content.

    :return: UserDataTypeAndDecodedContent
    :raises: SchemaValidationError when non-jinja content found but
        header declared ## template: jinja.
    :raises JinjaSyntaxParsingException when jinja syntax error found.
    :raises JinjaLoadError when jinja template fails to load.
    """
    from cloudinit.handlers.jinja_template import (
        JinjaLoadError,
        JinjaSyntaxParsingException,
        NotJinjaError,
        render_jinja_payload_from_file,
    )

    user_data_type = type_from_starts_with(content)
    schema_position = "format-l1.c1"
    if user_data_type == "text/jinja2":
        try:
            content = render_jinja_payload_from_file(
                content, config_path, instance_data_path
            )
        except NotJinjaError as e:
            raise SchemaValidationError(
                [
                    SchemaProblem(
                        schema_position,
                        "Detected type '{user_data_type}' from header. "
                        "But, content is not a jinja template",
                    )
                ]
            ) from e
        except JinjaSyntaxParsingException as e:
            error(
                "Failed to render templated user-data. " + str(e),
                sys_exit=True,
            )
        except JinjaLoadError as e:
            error(str(e), sys_exit=True)
        schema_position = "format-l2.c1"
        user_data_type = type_from_starts_with(content)
    if not user_data_type:  # Neither jinja2 nor #cloud-config
        header_line, _, _ = content.partition("\n")
        raise SchemaValidationInvalidHeaderError(
            [
                SchemaProblem(
                    schema_position,
                    f"Unrecognized user-data header in {config_path}:"
                    f' "{header_line}".\nExpected first line'
                    f" to be one of: {', '.join(USERDATA_VALID_HEADERS)}",
                )
            ]
        )
    elif user_data_type != "text/cloud-config":
        print(
            f"User-data type '{user_data_type}' not currently evaluated"
            " by cloud-init schema"
        )
    return UserDataTypeAndDecodedContent(user_data_type, content)


def validate_cloudconfig_file(
    config_path: str,
    schema: dict,
    schema_type: SchemaType = SchemaType.CLOUD_CONFIG,
    annotate: bool = False,
    instance_data_path: Optional[str] = None,
) -> bool:
    """Validate cloudconfig file adheres to a specific jsonschema.

    @param config_path: Path to the yaml cloud-config file to parse, or None
        to default to system userdata from Paths object.
    @param schema: Dict describing a valid jsonschema to validate against.
    @param schema_type: One of SchemaType.NETWORK_CONFIG or CLOUD_CONFIG
    @param annotate: Boolean set True to print original config file with error
        annotations on the offending lines.
    @param instance_data_path: Path to instance_data JSON, used for text/jinja
        rendering.

    :return: True when validation was performed successfully
    :raises SchemaValidationError containing any of schema_errors encountered.
    :raises RuntimeError when config_path does not exist.
    """
    from cloudinit.net.netplan import available as netplan_available

    decoded_content = load_text_file(config_path)
    if not decoded_content:
        print(
            "Empty '%s' found at %s. Nothing to validate."
            % (schema_type.value, config_path)
        )
        return False

    if schema_type in (SchemaType.NETWORK_CONFIG,):
        decoded_config = UserDataTypeAndDecodedContent(
            schema_type.value, decoded_content
        )
    else:
        decoded_config = _get_config_type_and_rendered_userdata(
            config_path, decoded_content, instance_data_path
        )
    if decoded_config.userdata_type not in (
        "network-config",
        "text/cloud-config",
    ):
        return False
    content = decoded_config.content
    errors = process_merged_cloud_config_part_problems(content)
    try:
        if annotate:
            cloudconfig, marks = safeyaml.load_with_marks(content)
        else:
            cloudconfig = yaml.safe_load(content)
            marks = {}
    except yaml.YAMLError as e:
        line = column = 1
        mark = None
        if hasattr(e, "context_mark") and getattr(e, "context_mark"):
            mark = getattr(e, "context_mark")
        elif hasattr(e, "problem_mark") and getattr(e, "problem_mark"):
            mark = getattr(e, "problem_mark")
        if mark:
            line = mark.line + 1
            column = mark.column + 1
        errors.append(
            SchemaProblem(
                "format-l{line}.c{col}".format(line=line, col=column),
                "File {0} is not valid YAML. {1}".format(config_path, str(e)),
            ),
        )
        schema_error = SchemaValidationError(errors)
        if annotate:
            print(
                annotated_cloudconfig_file(
                    {}, content, {}, schema_errors=schema_error.schema_errors
                )
            )
        raise schema_error from e
    if not isinstance(cloudconfig, dict):
        # Return a meaningful message on empty cloud-config
        if not annotate:
            raise RuntimeError(
                f"{schema_type.value} {config_path} is not a YAML dict."
            )
    if schema_type == SchemaType.NETWORK_CONFIG:
        if not cloudconfig.get("network", cloudconfig):
            print("Skipping network-config schema validation on empty config.")
            return False
        network_version = network_schema_version(cloudconfig)
        if network_version == 2:
            schema_type = SchemaType.NETWORK_CONFIG_V2
            if netplan_validate_network_schema(
                network_config=cloudconfig, strict=True, annotate=annotate
            ):
                return True  # schema validation performed by netplan
            elif netplan_available():
                print(
                    "Skipping network-config schema validation for version: 2."
                    " No netplan API available."
                )
                return False
        elif network_version == 1:
            schema_type = SchemaType.NETWORK_CONFIG_V1
            # refresh schema since NETWORK_CONFIG defaults to V2
            schema = get_schema(schema_type)
    try:
        if not validate_cloudconfig_schema(
            cloudconfig,
            schema=schema,
            schema_type=schema_type,
            strict=True,
            log_deprecations=False,
        ):
            print(
                f"Skipping {schema_type.value} schema validation."
                " Jsonschema dependency missing."
            )
            return False
    except SchemaValidationError as e:
        if e.has_errors():
            errors += e.schema_errors
        if annotate:
            print(
                annotated_cloudconfig_file(
                    cloudconfig,
                    content,
                    marks,
                    schema_errors=errors,
                    schema_deprecations=e.schema_deprecations,
                )
            )
        elif e.schema_deprecations:
            message = _format_schema_problems(
                e.schema_deprecations,
                prefix="Cloud config schema deprecations: ",
                separator=", ",
            )
            print(message)
        if errors:
            raise SchemaValidationError(schema_errors=errors) from e
    return True


def _sort_property_order(value):
    """Provide a sorting weight for documentation of property types.

    Weight values ensure 'array' sorted after 'object' which is sorted
    after anything else which remains unsorted.
    """
    if value == "array":
        return 2
    elif value == "object":
        return 1
    return 0


def _flatten(xs):
    for x in xs:
        if isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
            yield from _flatten(x)
        else:
            yield x


def _collect_subschema_types(property_dict: dict, multi_key: str) -> List[str]:
    property_types = []
    for subschema in property_dict.get(multi_key, {}):
        if subschema.get(DEPRECATED_KEY):  # don't document deprecated types
            continue
        if subschema.get("enum"):
            property_types.extend(
                [
                    f"``{_YAML_MAP.get(enum_value, enum_value)}``"
                    for enum_value in subschema.get("enum", [])
                ]
            )
        elif subschema.get("type"):
            property_types.append(subschema["type"])
    return list(_flatten(property_types))


def _get_property_type(property_dict: dict, defs: dict) -> str:
    """Return a string representing a property type from a given
    jsonschema.
    """
    flatten_schema_refs(property_dict, defs)
    property_types = property_dict.get("type", [])
    if not isinstance(property_types, list):
        property_types = [property_types]
    # A property_dict cannot have simultaneously more than one of these props
    if property_dict.get("enum"):
        property_types = [
            f"``{_YAML_MAP.get(k, k)}``" for k in property_dict["enum"]
        ]
    elif property_dict.get("oneOf"):
        property_types.extend(_collect_subschema_types(property_dict, "oneOf"))
    elif property_dict.get("anyOf"):
        property_types.extend(_collect_subschema_types(property_dict, "anyOf"))
    if len(property_types) == 1:
        property_type = property_types[0]
    else:
        property_types.sort(key=_sort_property_order)
        property_type = "/".join(property_types)
    items = property_dict.get("items", {})
    sub_property_types = items.get("type", [])
    if not isinstance(sub_property_types, list):
        sub_property_types = [sub_property_types]
    # Collect each item type
    prune_undefined = bool(sub_property_types)
    for sub_item in chain(items.get("oneOf", {}), items.get("anyOf", {})):
        sub_type = _get_property_type(sub_item, defs)
        if prune_undefined and sub_type == "UNDEFINED":
            # If the main object has a type, then sub-schemas are allowed to
            # omit the type. Prune subschema undefined types.
            continue
        sub_property_types.append(sub_type)
    if sub_property_types:
        if len(sub_property_types) == 1:
            return f"{property_type} of {sub_property_types[0]}"
        sub_property_types.sort(key=_sort_property_order)
        sub_property_doc = f"({'/'.join(sub_property_types)})"
        return f"{property_type} of {sub_property_doc}"
    return property_type or "UNDEFINED"


def _parse_description(description, prefix) -> str:
    """Parse description from the meta in a format that we can better
    display in our docs. This parser does three things:

    - Guarantee that a paragraph will be in a single line
    - Guarantee that each new paragraph will be aligned with
      the first paragraph
    - Proper align lists of items

    @param description: The original description in the meta.
    @param prefix: The number of spaces used to align the current description
    """
    list_paragraph = prefix
    description = re.sub(r"(\S)\n(\S)", r"\1 \2", description)
    description = re.sub(r"\n\n", r"\n\n{}".format(prefix), description)
    description = re.sub(
        r"\n( +)-", r"\n{}-".format(list_paragraph), description
    )

    return description


def flatten_schema_refs(src_cfg: dict, defs: dict):
    """Flatten schema: replace $refs in src_cfg with definitions from $defs."""
    if "$ref" in src_cfg:
        reference = src_cfg.pop("$ref").replace("#/$defs/", "")
        # Update the defined references in subschema for doc rendering
        src_cfg.update(defs[reference])
    if "items" in src_cfg:
        if "$ref" in src_cfg["items"]:
            reference = src_cfg["items"].pop("$ref").replace("#/$defs/", "")
            # Update the references in subschema for doc rendering
            src_cfg["items"].update(defs[reference])
        if "oneOf" in src_cfg["items"]:
            for sub_schema in src_cfg["items"]["oneOf"]:
                if "$ref" in sub_schema:
                    reference = sub_schema.pop("$ref").replace("#/$defs/", "")
                    sub_schema.update(defs[reference])
    for sub_schema in chain(
        src_cfg.get("oneOf", []),
        src_cfg.get("anyOf", []),
        src_cfg.get("allOf", []),
    ):
        if "$ref" in sub_schema:
            reference = sub_schema.pop("$ref").replace("#/$defs/", "")
            sub_schema.update(defs[reference])


def flatten_schema_all_of(src_cfg: dict):
    """Flatten schema: Merge allOf.

    If a schema as allOf, then all of the sub-schemas must hold. Therefore
    it is safe to merge them.
    """
    sub_schemas = src_cfg.pop("allOf", None)
    if not sub_schemas:
        return
    for sub_schema in sub_schemas:
        src_cfg.update(sub_schema)


def _get_property_description(prop_config: dict) -> str:
    """Return accumulated property description.

    Account for the following keys:
    - top-level description key
    - any description key present in each subitem under anyOf or allOf

    Order and deprecated property description after active descriptions.
    Add a trailing stop "." to any description not ending with ":".
    """

    def assign_descriptions(
        config: dict, descriptions: list, deprecated_descriptions: list
    ):
        if any(
            map(
                config.get,
                ("deprecated_version", "changed_version", "new_version"),
            )
        ):
            deprecated_descriptions.append(
                _add_deprecated_changed_or_new_msg(config)
            )
        elif config.get("description"):
            descriptions.append(_add_deprecated_changed_or_new_msg(config))

    oneOf = prop_config.get("oneOf", {})
    anyOf = prop_config.get("anyOf", {})
    descriptions: list = []
    deprecated_descriptions: list = []

    assign_descriptions(prop_config, descriptions, deprecated_descriptions)
    for sub_item in chain(oneOf, anyOf):
        assign_descriptions(sub_item, descriptions, deprecated_descriptions)

    # order deprecated descrs last
    description = ". ".join(chain(descriptions, deprecated_descriptions))
    if description:
        description = f" {description}"
    return description


def _get_property_doc(schema: dict, defs: dict, prefix="   ") -> str:
    """Return restructured text describing the supported schema properties."""
    new_prefix = prefix + "  "
    properties = []
    if schema.get("hidden") is True:
        return ""  # no docs for this schema
    property_keys = [
        key
        for key in ("properties", "patternProperties")
        if "hidden" not in schema or key not in schema["hidden"]
    ]
    property_schemas = [schema.get(key, {}) for key in property_keys]

    for prop_schema in property_schemas:
        for prop_key, prop_config in prop_schema.items():
            flatten_schema_refs(prop_config, defs)
            flatten_schema_all_of(prop_config)
            if prop_config.get("hidden") is True:
                continue  # document nothing for this property

            description = _get_property_description(prop_config)

            # Define prop_name and description for SCHEMA_PROPERTY_TMPL
            label = prop_config.get("label", prop_key)
            properties.append(
                SCHEMA_PROPERTY_TMPL.format(
                    prefix=prefix,
                    prop_name=label,
                    description=_parse_description(description, prefix + "  "),
                    prop_type=_get_property_type(prop_config, defs),
                )
            )
            items = prop_config.get("items")
            if items:
                flatten_schema_refs(items, defs)
                if items.get("properties") or items.get("patternProperties"):
                    properties.append(
                        SCHEMA_LIST_ITEM_TMPL.format(
                            prefix=new_prefix, prop_name=label
                        )
                    )
                    properties.append(
                        _get_property_doc(items, defs=defs, prefix=new_prefix)
                    )
                for alt_schema in items.get("oneOf", []):
                    if alt_schema.get("properties") or alt_schema.get(
                        "patternProperties"
                    ):
                        properties.append(
                            SCHEMA_LIST_ITEM_TMPL.format(
                                prefix=new_prefix, prop_name=label
                            )
                        )
                        properties.append(
                            _get_property_doc(
                                alt_schema, defs=defs, prefix=new_prefix
                            )
                        )
            if (
                "properties" in prop_config
                or "patternProperties" in prop_config
            ):
                properties.append(
                    _get_property_doc(
                        prop_config, defs=defs, prefix=new_prefix
                    )
                )
    return "\n\n".join(properties)


def _get_examples(meta: MetaSchema) -> str:
    """Return restructured text describing the meta examples if present."""
    paths = read_cfg_paths()
    module_docs_dir = os.path.join(paths.docs_dir, "module-docs")
    examples = meta.get("examples")
    if not examples:
        return ""
    rst_content: str = ""
    for example in examples:
        # FIXME(drop conditional when all mods have rtd/module-doc/*/data.yaml)
        if isinstance(example, dict):
            if example["comment"]:
                comment = f"# {example['comment']}\n"
            else:
                comment = ""
            example = comment + load_text_file(
                os.path.join(module_docs_dir, example["file"])
            )
        indented_lines = textwrap.indent(example, "   ").split("\n")
        rst_content += "\n".join(indented_lines)
    return rst_content


def _get_activate_by_schema_keys_doc(meta: MetaSchema) -> str:
    if not meta.get("activate_by_schema_keys"):
        return ""
    schema_keys = ", ".join(
        f"``{k}``" for k in meta["activate_by_schema_keys"]
    )
    return f"**Activate only on keys:** {schema_keys}\n\n"


def get_meta_doc(meta: MetaSchema, schema: Optional[dict] = None) -> str:
    """Return reStructured text rendering the provided metadata.

    @param meta: Dict of metadata to render.
    @param schema: Optional module schema, if absent, read global schema.
    @raise KeyError: If metadata lacks an expected key.
    """

    if schema is None:
        schema = get_schema()
    if not meta or not schema:
        raise ValueError("Expected non-empty meta and schema")
    keys = set(meta.keys())
    required_keys = {
        "id",
        "title",
        "examples",
        "frequency",
        "distros",
        "description",
        "name",
    }
    optional_keys = {"activate_by_schema_keys"}
    error_message = ""
    if required_keys - keys:
        error_message = "Missing required keys in module meta: {}".format(
            required_keys - keys
        )
    elif keys - required_keys - optional_keys:
        error_message = (
            "Additional unexpected keys found in module meta: {}".format(
                keys - required_keys
            )
        )
    if error_message:
        raise KeyError(error_message)

    # cast away type annotation
    meta_copy = dict(deepcopy(meta))
    meta_copy["property_header"] = ""
    meta_copy["prefix6"] = "      "
    meta_copy["prefix3"] = "   "
    meta_copy["description"] = textwrap.indent(
        cast(str, meta_copy["description"]), "      "
    )
    defs = schema.get("$defs", {})
    if defs.get(meta["id"]):
        schema = defs.get(meta["id"], {})
        schema = cast(dict, schema)
    if any(schema["properties"].values()):
        try:
            meta_copy["property_doc"] = _get_property_doc(
                schema, defs=defs, prefix="      "
            )
        except AttributeError:
            LOG.warning("Unable to render property_doc due to invalid schema")
            meta_copy["property_doc"] = ""
    if not meta_copy.get("property_doc", ""):
        meta_copy[
            "property_doc"
        ] = "      No schema definitions for this module"
    meta_copy["examples"] = textwrap.indent(_get_examples(meta), "      ")
    if not meta_copy["examples"]:
        meta_copy["examples"] = "         No examples for this module"
    meta_copy["distros"] = ", ".join(meta["distros"])
    # Need an underbar of the same length as the name
    meta_copy["title_underbar"] = re.sub(r".", "-", meta["name"])
    meta_copy["activate_by_schema_keys"] = _get_activate_by_schema_keys_doc(
        meta
    )
    template = SCHEMA_DOC_TMPL.format(**meta_copy)
    return template


def get_modules() -> dict:
    configs_dir = os.path.dirname(os.path.abspath(__file__))
    return get_modules_from_dir(configs_dir)


def load_doc(requested_modules: list) -> str:
    """Load module docstrings

    Docstrings are generated on module load. Reduce, reuse, recycle.
    """
    docs = ""
    all_modules = list(get_modules().values()) + ["all"]
    invalid_docs = set(requested_modules).difference(set(all_modules))
    if invalid_docs:
        error(
            "Invalid --docs value {}. Must be one of: {}".format(
                list(invalid_docs),
                ", ".join(all_modules),
            ),
            sys_exit=True,
        )
    module_docs = get_module_docs()
    schema = get_schema()
    for mod_name in sorted(all_modules):
        if "all" in requested_modules or mod_name in requested_modules:
            (mod_locs, _) = importer.find_module(
                mod_name, ["cloudinit.config"], ["meta"]
            )
            if mod_locs:
                mod = importer.import_module(mod_locs[0])
                if module_docs.get(mod.meta["id"]):
                    # Include docs only when module id is in module_docs
                    mod.meta.update(module_docs.get(mod.meta["id"], {}))
                    docs += get_meta_doc(mod.meta, schema) or ""
                else:
                    docs += mod.__doc__ or ""
    return docs


def get_schema_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas")


def get_module_docs() -> dict:
    """Return a dict keyed on cc_<mod_name> with documentation info"""
    paths = read_cfg_paths()
    mod_docs = {}
    module_docs_dir = os.path.join(paths.docs_dir, "module-docs")
    for mod_doc in glob.glob(f"{module_docs_dir}/*/data.yaml"):
        mod_docs.update(load_yaml(load_text_file(mod_doc)))
    return mod_docs


def get_schema(schema_type: SchemaType = SchemaType.CLOUD_CONFIG) -> dict:
    """Return jsonschema for a specific type.

    Return empty schema when no specific schema file exists.
    """
    schema_file = os.path.join(
        get_schema_dir(), SCHEMA_FILES_BY_TYPE[schema_type]["latest"]
    )
    full_schema = None
    try:
        full_schema = json.loads(load_text_file(schema_file))
    except (IOError, OSError):
        LOG.warning(
            "Skipping %s schema validation. No JSON schema file found %s.",
            schema_type.value,
            schema_file,
        )
        return {}
    return full_schema


def get_parser(parser=None):
    """Return a parser for supported cmdline arguments."""
    if not parser:
        parser = argparse.ArgumentParser(
            prog="cloudconfig-schema",
            description=(
                "Schema validation and documentation of instance-data"
                " configuration provided to cloud-init. This includes:"
                " user-data, vendor-data and network-config"
            ),
        )
    parser.add_argument(
        "-c",
        "--config-file",
        help=(
            "Path of the cloud-config or network-config YAML file to validate"
        ),
    )
    parser.add_argument(
        "-t",
        "--schema-type",
        type=str,
        choices=[
            SchemaType.CLOUD_CONFIG.value,
            SchemaType.NETWORK_CONFIG.value,
        ],
        help=(
            "When providing --config-file, the schema type to validate config"
            f" against. Default: {SchemaType.CLOUD_CONFIG}"
        ),
    )
    parser.add_argument(
        "-i",
        "--instance-data",
        type=str,
        help=(
            "Path to instance-data.json file for variable expansion "
            "of '##template: jinja' user-data. Default: "
            f"{read_cfg_paths().get_runpath('instance_data')}"
        ),
    )
    parser.add_argument(
        "--system",
        action="store_true",
        default=False,
        help=(
            "Validate the system instance-data provided as vendor-data"
            " user-data and network-config"
        ),
    )
    parser.add_argument(
        "-d",
        "--docs",
        nargs="+",
        help=(
            "Print schema module docs. Choices: all or"
            " space-delimited cc_names."
        ),
    )
    parser.add_argument(
        "--annotate",
        action="store_true",
        default=False,
        help="Annotate existing instance-data files any discovered errors",
    )
    return parser


def _assert_exclusive_args(args):
    """Error or warn on invalid exclusive parameter combinations."""
    exclusive_args = [args.config_file, args.docs, args.system]
    if len([arg for arg in exclusive_args if arg]) != 1:
        error(
            "Expected one of --config-file, --system or --docs arguments",
            sys_exit=True,
        )
    if any([args.system, args.docs]) and args.schema_type:
        print(
            "WARNING: The --schema-type parameter is inapplicable when either"
            " --system or --docs present"
        )
    if args.annotate and args.docs:
        error(
            "Invalid flag combination. Cannot use --annotate with --docs",
            sys_exit=True,
        )


def get_config_paths_from_args(
    args,
) -> Tuple[str, List[InstanceDataPart]]:
    """Return appropriate instance-data.json and instance data parts

    Based on command line args, and user permissions, determine the
    appropriate instance-data.json to source for jinja templates and
    a list of applicable InstanceDataParts such as user-data, vendor-data
    and network-config for which to validate schema. Avoid returning any
    InstanceDataParts when the expected config_path does not exist.

    :return: A tuple of the instance-data.json path and a list of
        viable InstanceDataParts present on the system.
    """

    def get_processed_or_fallback_path(
        paths: Paths,
        primary_path_key: str,
        raw_fallback_path_key: str,
    ) -> str:
        """Get processed data path when non-empty of fallback to raw data path.

        - When primary path and raw path exist and are empty, prefer primary
          path.
        - When primary path is empty but the raw fallback path is non-empty,
          this indicates an invalid and ignored raw user-data was provided and
          cloud-init emitted a warning and did not process unknown raw
          user-data.
          In the case of invalid raw user-data header, prefer
          raw_fallback_path_key so actionable sensible warnings can be
          reported to the user about the raw unparsable user-data.
        """
        primary_datapath = paths.get_ipath(primary_path_key) or ""
        with suppress(FileNotFoundError):
            if not os.stat(primary_datapath).st_size:
                raw_path = paths.get_ipath(raw_fallback_path_key) or ""
                if os.stat(raw_path).st_size:
                    return raw_path
        return primary_datapath

    try:
        paths = read_cfg_paths(fetch_existing_datasource="trust")
    except (IOError, OSError) as e:
        if e.errno == EACCES:
            LOG.debug(
                "Using default instance-data/user-data paths for non-root user"
            )
            paths = read_cfg_paths()
        else:
            raise
    except DataSourceNotFoundException:
        paths = read_cfg_paths()
        LOG.warning(
            "datasource not detected, using default"
            " instance-data/user-data paths."
        )
    if args.instance_data:
        instance_data_path = args.instance_data
    elif os.getuid() != 0:
        instance_data_path = paths.get_runpath("instance_data")
    else:
        instance_data_path = paths.get_runpath("instance_data_sensitive")
    config_files: List[InstanceDataPart] = []
    if args.config_file:
        if args.schema_type:
            schema_type = SchemaType(args.schema_type)
        else:
            schema_type = SchemaType.CLOUD_CONFIG
        if schema_type == SchemaType.NETWORK_CONFIG:
            instancedata_type = InstanceDataType.NETWORK_CONFIG
        else:
            instancedata_type = InstanceDataType.USERDATA
        config_files.append(
            InstanceDataPart(instancedata_type, schema_type, args.config_file)
        )
    else:
        if os.getuid() != 0:
            error(
                "Unable to read system userdata or vendordata as non-root"
                " user. Try using sudo.",
                sys_exit=True,
            )
        userdata_file = get_processed_or_fallback_path(
            paths, "cloud_config", "userdata_raw"
        )
        config_files.append(
            InstanceDataPart(
                InstanceDataType.USERDATA,
                SchemaType.CLOUD_CONFIG,
                userdata_file,
            )
        )
        supplemental_config_files: List[InstanceDataPart] = [
            InstanceDataPart(
                InstanceDataType.VENDORDATA,
                SchemaType.CLOUD_CONFIG,
                get_processed_or_fallback_path(
                    paths, "vendor_cloud_config", "vendordata_raw"
                ),
            ),
            InstanceDataPart(
                InstanceDataType.VENDOR2DATA,
                SchemaType.CLOUD_CONFIG,
                get_processed_or_fallback_path(
                    paths, "vendor2_cloud_config", "vendordata2_raw"
                ),
            ),
            InstanceDataPart(
                InstanceDataType.NETWORK_CONFIG,
                SchemaType.NETWORK_CONFIG,
                paths.get_ipath("network_config") or "",
            ),
        ]
        for data_part in supplemental_config_files:
            if data_part.config_path and os.path.exists(data_part.config_path):
                config_files.append(data_part)
    if not os.path.exists(config_files[0].config_path):
        error(
            f"Config file {config_files[0].config_path} does not exist",
            fmt="Error: {}",
            sys_exit=True,
        )
    return instance_data_path, config_files


def handle_schema_args(name, args):
    """Handle provided schema args and perform the appropriate actions."""
    _assert_exclusive_args(args)
    full_schema = get_schema()
    if args.docs:
        print(load_doc(args.docs))
        return
    instance_data_path, config_files = get_config_paths_from_args(args)

    nested_output_prefix = ""
    multi_config_output = bool(len(config_files) > 1)
    if multi_config_output:
        print(
            "Found cloud-config data types: %s"
            % ", ".join(str(cfg_part.config_type) for cfg_part in config_files)
        )
        nested_output_prefix = "  "

    error_types = []
    for idx, cfg_part in enumerate(config_files, 1):
        performed_schema_validation = False
        if multi_config_output:
            print(
                f"\n{idx}. {cfg_part.config_type} at {cfg_part.config_path}:"
            )
        if cfg_part.schema_type == SchemaType.NETWORK_CONFIG:
            cfg_schema = get_schema(cfg_part.schema_type)
        else:
            cfg_schema = full_schema
        try:
            performed_schema_validation = validate_cloudconfig_file(
                cfg_part.config_path,
                cfg_schema,
                cfg_part.schema_type,
                args.annotate,
                instance_data_path,
            )
        except SchemaValidationError as e:
            if not args.annotate:
                print(
                    f"{nested_output_prefix}Invalid"
                    f" {cfg_part.config_type} {cfg_part.config_path}"
                )
                error(
                    str(e),
                    fmt=nested_output_prefix + "Error: {}\n",
                )
            error_types.append(cfg_part.config_type)
        except RuntimeError as e:
            print(f"{nested_output_prefix}Invalid {cfg_part.config_type!s}")
            error(str(e), fmt=nested_output_prefix + "Error: {}\n")
            error_types.append(cfg_part.config_type)
        else:
            if performed_schema_validation:
                if args.config_file:
                    cfg = cfg_part.config_path
                else:
                    cfg = cfg_part.config_type
                print(f"{nested_output_prefix}Valid schema {cfg!s}")
    if error_types:
        error(
            ", ".join(str(error_type) for error_type in error_types),
            fmt="Error: Invalid schema: {}\n",
            sys_exit=True,
        )


def main():
    """Tool to validate schema of a cloud-config file or print schema docs."""
    parser = get_parser()
    handle_schema_args("cloudconfig-schema", parser.parse_args())
    return 0


if __name__ == "__main__":
    sys.exit(main())
