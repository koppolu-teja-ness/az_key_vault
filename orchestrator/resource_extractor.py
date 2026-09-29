"""Extracts the set of Azure resource types referenced by a compiled ARM template."""
from __future__ import annotations


def extract_resource_types(arm_template: dict) -> list[str]:
    """Return the distinct resource types used, including nested child resources."""
    types: set[str] = set()

    def _walk(resources: list[dict]) -> None:
        for resource in resources:
            resource_type = resource.get("type")
            if resource_type:
                types.add(resource_type)
            _walk(resource.get("resources", []))

    _walk(arm_template.get("resources", []))
    return sorted(types)
