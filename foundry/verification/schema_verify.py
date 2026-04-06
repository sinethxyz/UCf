"""Schema verification: OpenAPI spec and JSON Schema validation."""


async def verify_openapi(spec_path: str) -> dict:
    """Validate an OpenAPI specification file.

    Args:
        spec_path: Path to the OpenAPI YAML/JSON file.

    Returns:
        Validation result dict.
    """
    raise NotImplementedError


async def verify_json_schema(data: dict, schema_path: str) -> dict:
    """Validate data against a JSON Schema.

    Args:
        data: The data to validate.
        schema_path: Path to the JSON Schema file.

    Returns:
        Validation result dict with passed and errors.
    """
    raise NotImplementedError
