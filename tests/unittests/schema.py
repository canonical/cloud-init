from copy import deepcopy


class JsonLocalResolver:
    def __init__(self, schema: dict):
        from jsonschema import RefResolver

        self._schema = schema
        self._resolver = RefResolver.from_schema(schema)

    def _do_resolve(self, node):
        if "$ref" in node:
            ref = node["$ref"]
            if ref[0] != "#" or ref == "#":
                return  # Do only resolve non-recursive local references
            with self._resolver.resolving(ref) as resolved:
                self._local_resolve(resolved)
                del node["$ref"]
                node.update(resolved)

    def _local_resolve(self, node):
        """Resolve in-place non-recursive local references

        :param node: The node to resolve.
        """
        if isinstance(node, list):
            for item in node:
                self._local_resolve(item)
            return
        if isinstance(node, dict):
            self._do_resolve(node)
            for value in node.values():
                self._local_resolve(value)

    def resolve(self) -> dict:
        """Resolve all local json-references in a schema

        :return: The resolved JSON Schema.
        """
        schema = deepcopy(self._schema)
        self._local_resolve(schema)
        del schema["$defs"]
        return schema
