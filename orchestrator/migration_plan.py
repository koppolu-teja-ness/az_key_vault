"""Migration plan: the structured artifact the LLM produces after reasoning over
the cloud-neutral representation (CNR). It captures *what* AWS resources should
exist and how their properties map from the source -- not template syntax or
formatting. Rendering that plan into an actual template is a separate, mechanical
step (see cfn_generator.py). Keeping the two apart is what makes it possible to
add a second target generator (Terraform, GCP Deployment Manager, ...) later
without touching the reasoning step, and to validate/repair the plan itself
independently of template syntax.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .cloud_neutral import CloudNeutralRepresentation


class MigrationPlanError(RuntimeError):
    pass


@dataclass
class PlannedResource:
    logical_id: str
    aws_type: str
    properties: dict
    depends_on: list[str] = field(default_factory=list)
    source_azure_type: str = ""


@dataclass
class MigrationPlan:
    description: str
    parameters: dict
    conditions: dict
    resources: list[PlannedResource]
    outputs: dict


PLAN_JSON_SCHEMA_HINT = """Return ONLY a single JSON object (no markdown fences, no \
commentary) with this exact shape:
{
  "description": "short description of the stack",
  "parameters": {"<CfnParamName>": {"Type": "...", "Default": "...", "NoEcho": true}},
  "conditions": {"<ConditionName>": "CFN condition function JSON, e.g. {\"Fn::Equals\": [{\"Ref\": \"Param\"}, \"\"]}"},
  "resources": [
    {
      "logical_id": "MyVault",
      "aws_type": "AWS::SecretsManager::Secret",
      "source_azure_type": "Microsoft.KeyVault/vaults/secrets",
      "properties": {"...": "may use CFN long-form intrinsics as JSON, e.g. {\\"Fn::Sub\\": \\"...\\"} or {\\"Ref\\": \\"Param\\"}"},
      "depends_on": ["OtherLogicalId"]
    }
  ],
  "outputs": {"<OutputName>": {"Value": "...", "Description": "..."}}
}
Every condition name referenced via {"Fn::If": ["ConditionName", ...]} anywhere in \
properties MUST have a matching entry in "conditions" -- never reference an \
undeclared condition."""


def build_migration_plan_prompt(
    cnr: CloudNeutralRepresentation, mapping_docs: dict[str, str]
) -> str:
    cnr_json = json.dumps(
        {
            "parameters": [vars(p) for p in cnr.parameters],
            "resources": [vars(r) for r in cnr.resources],
            "outputs": cnr.outputs,
        },
        indent=2,
        default=str,
    )
    docs_section = "\n\n".join(
        f"### Reference doc for {rtype}\n{doc}" for rtype, doc in mapping_docs.items()
    )
    return f"""You are reasoning about migrating Azure infrastructure to AWS. You are \
given a cloud-neutral representation (CNR) of the source resources -- already \
normalized out of Bicep/ARM syntax -- plus reference docs mapping each Azure \
resource type to its AWS equivalent.

Produce a MIGRATION PLAN describing the target AWS resources, their properties, \
and how each maps back to its source resource. Do NOT produce CloudFormation \
YAML or any template syntax yourself; a separate deterministic generator turns \
your plan into the final template.

## Cloud-neutral representation
```json
{cnr_json}
```

## Mapping reference docs
{docs_section}

{PLAN_JSON_SCHEMA_HINT}
"""


def parse_migration_plan(raw_text: str) -> MigrationPlan:
    cleaned = _strip_markdown_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise MigrationPlanError(
            f"Migration plan is not valid JSON: {exc}\nRaw output:\n{raw_text}"
        ) from exc

    try:
        resources = [
            PlannedResource(
                logical_id=r["logical_id"],
                aws_type=r["aws_type"],
                properties=r.get("properties", {}) or {},
                depends_on=list(r.get("depends_on", []) or []),
                source_azure_type=r.get("source_azure_type", ""),
            )
            for r in data["resources"]
        ]
    except KeyError as exc:
        raise MigrationPlanError(f"Migration plan missing required field: {exc}") from exc

    conditions = data.get("conditions", {}) or {}
    referenced = set()
    for resource in resources:
        referenced |= _find_referenced_conditions(resource.properties)
    referenced |= _find_referenced_conditions(data.get("outputs", {}) or {})
    undeclared = sorted(referenced - conditions.keys())
    if undeclared:
        raise MigrationPlanError(
            "Migration plan references Fn::If condition(s) with no matching "
            f"entry in \"conditions\": {', '.join(undeclared)}"
        )

    return MigrationPlan(
        description=data.get("description", ""),
        parameters=data.get("parameters", {}) or {},
        conditions=conditions,
        resources=resources,
        outputs=data.get("outputs", {}) or {},
    )


def _find_referenced_conditions(value) -> set[str]:
    """Collect every condition name used via Fn::If anywhere inside value."""
    found: set[str] = set()
    if isinstance(value, dict):
        if_args = value.get("Fn::If")
        if isinstance(if_args, list) and if_args and isinstance(if_args[0], str):
            found.add(if_args[0])
        for v in value.values():
            found |= _find_referenced_conditions(v)
    elif isinstance(value, list):
        for v in value:
            found |= _find_referenced_conditions(v)
    return found


def _strip_markdown_fences(text: str) -> str:
    cleaned = text.strip().replace("\ufeff", "")
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.IGNORECASE | re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    return cleaned
