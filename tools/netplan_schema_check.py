import argparse
import os
import yaml

from jsonschema import Draft4Validator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="""
This script validates netplan example files against the cloud-init networkv2
schema.  The goal is to provide an easy way to track drift between networkv2
and netplan.

Netplan does not provide a centralized schema file to compare against directly,
but does maintain a reasonably comprehensive examples directory.  This script
relies on that directory to glean the netplan schema.
            """,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--schema-file",
        required=True,
        help="""
The cloud-init networkv2 schema file found in
cloudinit/config/schemas/schema-network-config-v2.json
in this repository.
        """,
    )
    parser.add_argument(
        "--netplan-examples",
        required=True,
        help="""
The examples/ directory in the netplan repo.  The most
recent netplan repo can be cloned from
https://github.com/canonical/netplan.
        """,
    )
    return parser.parse_args()


def validate_netplan_against_networkv2(schema_file, netplan_examples):
    """
    This script validates netplan example files against the cloud-init
    networkv2 schema.  The goal is to provide an easy way to track drift
    between networkv2 and netplan.

    Netplan does not provide a centralized schema file to compare against
    directly, but does maintain a reasonably comprehensive examples directory.
    This script relies on that directory to glean the netplan schema.

    There are two arguments required for this script.  The first is schema_file
    which should point to the cloud-init networkv2 schema file found in
    cloudinit/config/schemas/schema-network-config-v2.json in this repository.
    The second is netplan_examples which should point to the examples/
    directory in the netplan repo.  The most recent netplan repo can be cloned
    from https://github.com/canonical/netplan.
    """
    networkv2_schema = None
    with open(schema_file) as f:
        networkv2_schema = yaml.safe_load(f)
    validator = Draft4Validator(networkv2_schema)

    error_obj = {}
    for walk_tuple in os.walk(netplan_examples):
        filenames = walk_tuple[2]
        for fname in filenames:
            if fname.endswith(".yaml"):
                with open(netplan_examples + fname) as netplan_f:
                    netplan_example = yaml.safe_load(netplan_f)
                    errors = validator.iter_errors(netplan_example)
                    for e in errors:
                        schema_path_str = "-".join(map(str, e.schema_path))
                        if schema_path_str not in error_obj:
                            error_obj[schema_path_str] = {}
                        if e.message not in error_obj[schema_path_str]:
                            error_obj[schema_path_str][e.message] = set()
                        error_obj[schema_path_str][e.message].add(fname)

    # clean up error_obj for human readability
    for schema_path in error_obj:
        for message in error_obj[schema_path]:
            error_obj[schema_path][message] = list(
                error_obj[schema_path][message]
            )
    print(yaml.dump(error_obj))


if __name__ == "__main__":
    args = parse_args()
    validate_netplan_against_networkv2(args.schema_file, args.netplan_examples)
