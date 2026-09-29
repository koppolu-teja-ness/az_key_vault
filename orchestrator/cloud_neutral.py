"""Cloud-neutral representation (CNR): a normalized, provider-agnostic model of the
resources discovered in the source template, independent of Bicep/ARM's specific
JSON shape (apiVersion quirks, nested `resources[]`, expression syntax, etc).

This is the artifact that gets reasoned over by the LLM and by every downstream
generator (CloudFormation today, Terraform/GCP Deployment Manager tomorrow), so
adding a new source (e.g. Terraform HCL) or a new target only requires plugging
into this shape instead of re-deriving everything from raw ARM JSON again.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CNRParameter:
    name: str
    type: str
    default: object | None = None
    secure: bool = False


@dataclass
class CNRResource:
    logical_id: str
    azure_type: str
    api_version: str | None
    name_expression: object  # raw ARM "name" value, may be a literal or expression
    properties: dict
    depends_on: list[str] = field(default_factory=list)
    parent_logical_id: str | None = None


@dataclass
class CloudNeutralRepresentation:
    parameters: list[CNRParameter]
    resources: list[CNRResource]
    outputs: dict


def build_cnr(arm_template: dict) -> CloudNeutralRepresentation:
    """Convert a compiled ARM template into the cloud-neutral representation."""
    parameters = [
        CNRParameter(
            name=name,
            type=definition.get("type", "string"),
            default=definition.get("defaultValue"),
            secure="secure" in str(definition.get("type", "")).lower(),
        )
        for name, definition in (arm_template.get("parameters") or {}).items()
    ]

    resources: list[CNRResource] = []

    def _walk(arm_resources: list[dict], parent_logical_id: str | None) -> None:
        for resource in arm_resources:
            logical_id = _derive_logical_id(resource, parent_logical_id)
            resources.append(
                CNRResource(
                    logical_id=logical_id,
                    azure_type=resource.get("type", ""),
                    api_version=resource.get("apiVersion"),
                    name_expression=resource.get("name"),
                    properties=resource.get("properties", {}) or {},
                    depends_on=list(resource.get("dependsOn", []) or []),
                    parent_logical_id=parent_logical_id,
                )
            )
            _walk(resource.get("resources", []) or [], logical_id)

    _walk(arm_template.get("resources", []) or [], None)

    return CloudNeutralRepresentation(
        parameters=parameters,
        resources=resources,
        outputs=arm_template.get("outputs", {}) or {},
    )


def _derive_logical_id(resource: dict, parent_logical_id: str | None) -> str:
    """Best-effort stable logical id derived from the resource's declared name."""
    raw_name = str(resource.get("name", "")) or resource.get("type", "Resource")
    slug = "".join(ch for ch in raw_name if ch.isalnum()) or "Resource"
    slug = slug[0].upper() + slug[1:]
    return f"{parent_logical_id}{slug}" if parent_logical_id else slug
