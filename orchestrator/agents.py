"""The 7 migration agents, each a thin, testable function over MigrationState.

Deterministic stages (1, 2, 4, 5) wrap existing orchestrator modules unchanged;
only Agent 3 (mapping) calls the LLM. This keeps the same "LLM only reasons,
never emits template syntax" split as pipeline.py, just organized as discrete
agents instead of one linear function.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import os
import re
from pathlib import Path
from typing import Any

from .azure_export import AzureExportError, export_resource_group_to_bicep, fetch_resource_group_secret_values
from .bicep_compiler import BicepCompilerError, compile_bicep_to_arm
from .cfn_generator import generate_cloudformation
from .cloud_neutral import build_cnr, write_cnr
from .config import Config
from .generator import Generator, GeneratorNotConfiguredError
from .knowledge_base import KnowledgeBase
from .migration_plan import (
    MigrationPlanError,
    PLAN_JSON_SCHEMA_HINT,
    build_migration_plan_prompt,
    parse_migration_plan,
)
from .resource_extractor import extract_resource_types
from .state import MigrationState
from .validator import run_cfn_lint


def _log(agent: str, status: str, message: str) -> list[dict]:
    return [{"agent": agent, "status": status, "message": message}]


def _run_dir(state: MigrationState) -> Path:
    """Per-run artifact folder (CNR, migration plan, lint report, final report.md)."""
    run_dir = Path(state["output_dir"]) / "runs" / state["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


# ---------------------------------------------------------------------------
# Agent 0: export a live Azure resource group as the source .bicep file.
# Only runs when a resource_group was passed instead of an existing .bicep file.
# ---------------------------------------------------------------------------
def make_agent0_export_resource_group(input_dir: Path):
    def agent0_export_resource_group(state: MigrationState) -> dict:
        resource_group = state.get("resource_group")
        if not resource_group:
            return {
                "agent_log": _log(
                    "agent0_export_resource_group", "ok", "No resource group given; using the provided .bicep file."
                ),
            }

        print(f"\n[Agent 0] Exporting resource group '{resource_group}' from Azure...")
        try:
            bicep_path = export_resource_group_to_bicep(
                resource_group, input_dir, state.get("subscription_id")
            )
        except AzureExportError as exc:
            return {
                "stopped": True,
                "stop_reason": f"Resource group export failed: {exc}",
                "agent_log": _log("agent0_export_resource_group", "stopped", str(exc)),
            }

        # ARM/Bicep exports never include Key Vault secret values (Azure omits them from
        # the control-plane export API); read the real values from the data plane here so
        # agent6_deploy can carry them over instead of fabricating new ones.
        source_secret_values, source_vault_names, secret_fetch_warnings = fetch_resource_group_secret_values(
            resource_group, state.get("subscription_id")
        )
        log_entries = _log(
            "agent0_export_resource_group", "ok",
            f"Exported resource group '{resource_group}' to {bicep_path}. "
            f"Fetched {len(source_secret_values)} real secret value(s) from Key Vault.",
        )
        for warning in secret_fetch_warnings:
            print(f"[Agent 0] warning: {warning}")
            log_entries += _log("agent0_export_resource_group", "warning", warning)
        return {
            "bicep_path": str(bicep_path),
            "source_secret_values": source_secret_values,
            "source_vault_names": source_vault_names,
            "agent_log": log_entries,
        }

    return agent0_export_resource_group


# ---------------------------------------------------------------------------
# Agent 1: validate the Bicep file (compile + resource-support check).
# ---------------------------------------------------------------------------
def make_agent1_validate(knowledge_base: KnowledgeBase):
    def agent1_validate(state: MigrationState) -> dict:
        bicep_path = Path(state["bicep_path"])
        try:
            arm_template = compile_bicep_to_arm(bicep_path)
        except BicepCompilerError as exc:
            return {
                "stopped": True,
                "stop_reason": f"Bicep compilation failed: {exc}",
                "agent_log": _log("agent1_validate", "stopped", str(exc)),
            }

        resource_types = extract_resource_types(arm_template)
        supported_types = knowledge_base.supported_types()
        unsupported = [t for t in resource_types if t not in supported_types]

        base_update = {
            "arm_template": arm_template,
            "resource_types": resource_types,
            "supported_types": supported_types,
            "unsupported_types": unsupported,
        }

        if not resource_types:
            return {
                **base_update,
                "stopped": True,
                "stop_reason": "No resources found in the Bicep template.",
                "agent1_decision": "stopped",
                "agent_log": _log("agent1_validate", "stopped", "No resources found."),
            }

        if unsupported:
            print(
                f"\n[Agent 1] Unsupported resource type(s): {', '.join(unsupported)}\n"
                "These have no knowledge-base mapping doc yet."
            )
            answer = input("Continue migrating only the supported resources? [y/N] ").strip().lower()
            if answer != "y":
                return {
                    **base_update,
                    "stopped": True,
                    "stop_reason": f"Human stopped the run due to unsupported types: {', '.join(unsupported)}",
                    "agent1_decision": "stopped",
                    "agent_log": _log(
                        "agent1_validate", "stopped", "Human declined to continue with unsupported types."
                    ),
                }
            return {
                **base_update,
                "resource_types": [t for t in resource_types if t not in unsupported],
                "stopped": False,
                "agent1_decision": "human_approved",
                "agent_log": _log(
                    "agent1_validate", "warning", "Human approved continuing with unsupported types skipped."
                ),
            }

        return {
            **base_update,
            "stopped": False,
            "agent1_decision": "auto_continue",
            "agent_log": _log(
                "agent1_validate", "ok", f"All {len(resource_types)} resource type(s) supported."
            ),
        }

    return agent1_validate


# ---------------------------------------------------------------------------
# Agent 2: build the cloud-neutral representation (custom template per resource)

# ---------------------------------------------------------------------------
def agent2_build_cnr(state: MigrationState) -> dict:
    cnr = build_cnr(state["arm_template"])
    write_cnr(cnr, output_dir=str(_run_dir(state)))
    per_resource_templates = {
        r.logical_id: dataclasses.asdict(r)
        for r in cnr.resources
        if r.azure_type in state["resource_types"]
    }
    return {
        "cnr": cnr,
        "per_resource_templates": per_resource_templates,
        "agent_log": _log(
            "agent2_build_cnr", "ok", f"Built cloud-neutral templates for {len(per_resource_templates)} resource(s)."
        ),
    }


# ---------------------------------------------------------------------------
# Agent 3: LLM-reasoned mapping of each resource to its AWS equivalent.
# ---------------------------------------------------------------------------
def make_agent3_map_resources(knowledge_base: KnowledgeBase, generator: Generator):
    def agent3_map_resources(state: MigrationState) -> dict:
        lint_output = state.get("lint_output")
        fix_attempts = state.get("fix_attempts", 0)

        if lint_output and fix_attempts > 0:
            # Self-correction retry: feed the previous plan + lint failure back in.
            prompt = (
                f"The CloudFormation template rendered from your migration plan failed "
                f"cfn-lint with the following output:\n\n{lint_output}\n\n"
                f"Here is the migration plan JSON you produced:\n```json\n{state['migration_plan_raw']}\n```\n\n"
                f"Return a corrected migration plan fixing these issues.\n\n{PLAN_JSON_SCHEMA_HINT}"
            )
        else:
            mapping_docs = knowledge_base.load_docs(state["resource_types"])
            prompt = build_migration_plan_prompt(state["cnr"], mapping_docs)

        run_dir = _run_dir(state)
        (run_dir / "migration_prompt.txt").write_text(prompt, encoding="utf-8")

        raw_plan_text = generator.generate(prompt)
        try:
            plan = parse_migration_plan(raw_plan_text)
        except MigrationPlanError as exc:
            return {
                "migration_plan_raw": raw_plan_text,
                "stopped": True,
                "stop_reason": f"Migration plan invalid: {exc}",
                "agent_log": _log("agent3_map_resources", "failed", str(exc)),
            }

        (run_dir / "migration_plan.json").write_text(
            json.dumps(dataclasses.asdict(plan), indent=2, default=str), encoding="utf-8"
        )

        mapping_table = [
            {
                "logical_id": r.logical_id,
                "source_azure_type": r.source_azure_type,
                "aws_type": r.aws_type,
            }
            for r in plan.resources
        ]
        return {
            "migration_plan_raw": raw_plan_text,
            "migration_plan": plan,
            "mapping_table": mapping_table,
            "agent_log": _log(
                "agent3_map_resources", "ok", f"Mapped {len(mapping_table)} resource(s) to AWS equivalents."
            ),
        }

    return agent3_map_resources


# ---------------------------------------------------------------------------
# Plan approval gate: mandatory human review of the migration plan before any
# CloudFormation is generated.
# ---------------------------------------------------------------------------
def plan_approval_gate(state: MigrationState) -> dict:
    plan = state["migration_plan"]
    fix_attempts = state.get("fix_attempts", 0)
    if fix_attempts > 0:
        max_attempts = state.get("max_fix_attempts", 2)
        print(
            f"\n[Plan approval] Self-correction retry {fix_attempts}/{max_attempts} "
            f"(previous CloudFormation failed cfn-lint -- see below):"
        )
        if state.get("lint_output"):
            print(state["lint_output"].strip())
    print(f"\n[Plan approval] Migration plan: {plan.description or '(no description)'}")
    print(f"{'Logical ID':<24} {'Azure type':<32} {'AWS type':<32}")
    for m in state.get("mapping_table", []):
        print(f"{m['logical_id']:<24} {m['source_azure_type']:<32} {m['aws_type']:<32}")
    if plan.parameters:
        print(f"Parameters: {', '.join(plan.parameters.keys())}")
    if plan.outputs:
        print(f"Outputs: {', '.join(plan.outputs.keys())}")

    answer = input("\nApprove this migration plan and proceed to CloudFormation generation? [y/N] ").strip().lower()
    approved = answer == "y"
    update = {
        "plan_confirmed": approved,
        "agent_log": _log(
            "plan_approval_gate", "ok" if approved else "stopped",
            "Human approved the migration plan." if approved else "Human rejected the migration plan.",
        ),
    }
    if not approved:
        update["stopped"] = True
        update["stop_reason"] = "Human rejected the migration plan at the plan approval gate."
    return update


# ---------------------------------------------------------------------------
# Agent 4: deterministic render of the migration plan into CloudFormation YAML.
# ---------------------------------------------------------------------------
def make_agent4_render(output_dir: Path):
    def agent4_render(state: MigrationState) -> dict:
        yaml_text = generate_cloudformation(state["migration_plan"])
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{Path(state['bicep_path']).stem}.generated.yaml"
        output_path.write_text(yaml_text, encoding="utf-8")
        return {
            "cfn_yaml": yaml_text,
            "output_path": str(output_path),
            "agent_log": _log("agent4_render", "ok", f"Rendered CloudFormation template to {output_path}."),
        }

    return agent4_render


# ---------------------------------------------------------------------------
# Agent 5: validate the rendered template (cfn-lint).
# ---------------------------------------------------------------------------
def _count_lint_findings(lint_output: str) -> tuple[int, int]:
    """Count cfn-lint error (E####) vs. warning (W####) codes at line starts."""
    errors = len(re.findall(r"(?m)^E\d{4}", lint_output))
    warnings = len(re.findall(r"(?m)^W\d{4}", lint_output))
    return errors, warnings


def _render_validation_report(state: MigrationState, history: list[dict]) -> str:
    """Attempt-by-attempt trace of what cfn-lint checked and where it failed/passed."""
    max_attempts = state.get("max_fix_attempts", 2) + 1
    lines = [
        f"CFN VALIDATION REPORT -- run {state.get('run_id')}",
        f"Template: {state.get('output_path')}",
        "Tool: cfn-lint, run against the rendered template before any real AWS call.",
        "",
    ]
    for entry in history:
        result = "PASSED" if entry["passed"] else "FAILED"
        lines.append(
            f"Attempt {entry['attempt']}/{max_attempts} -- {result} "
            f"({entry['errors']} error(s), {entry['warnings']} warning(s))"
        )
        for out_line in entry["output"].splitlines():
            lines.append(f"  {out_line}")
        if not entry["passed"] and entry["attempt"] < max_attempts:
            lines.append("  -> Fed back to Agent 3 (LLM) for a corrected migration plan.")
        lines.append("")

    final = history[-1]
    if final["passed"]:
        retries = final["attempt"] - 1
        lines.append(
            "Final result: PASSED"
            + (f" after {retries} self-correction retry(ies)." if retries else " (first attempt).")
        )
    else:
        lines.append(f"Final result: FAILED after {final['attempt']} attempt(s) -- retries exhausted.")
    return "\n".join(lines) + "\n"


def agent5_validate_cfn(state: MigrationState) -> dict:
    lint_passed, lint_output = run_cfn_lint(Path(state["output_path"]))
    errors, warnings = _count_lint_findings(lint_output)
    attempt_entry = {
        "attempt": state.get("fix_attempts", 0) + 1,
        "passed": lint_passed,
        "errors": errors,
        "warnings": warnings,
        "output": lint_output.strip() or "(no findings)",
    }
    history = state.get("validation_history", []) + [attempt_entry]
    (_run_dir(state) / "cfn_validation_report.txt").write_text(
        _render_validation_report(state, history), encoding="utf-8"
    )
    status = "ok" if lint_passed else "warning"
    return {
        "lint_passed": lint_passed,
        "lint_output": lint_output,
        "lint_errors": errors,
        "lint_warnings": warnings,
        "validation_history": [attempt_entry],
        "agent_log": _log("agent5_validate_cfn", status, "cfn-lint passed." if lint_passed else lint_output),
    }


# ---------------------------------------------------------------------------
# Agent 6: deploy the validated template to AWS and verify it (real deploy).
# Fully automatic -- no human confirmation and no interactive value prompts.
# Parameter values are resolved from --params-file, CFN_PARAM_<NAME> env vars,
# the template's own Default, or (for NoEcho/secret params only) a securely
# generated random value; anything still unresolved or invalid fails the run
# fast instead of blocking on input().
# ---------------------------------------------------------------------------
def make_agent6_deploy(config: Config):
    def agent6_deploy(state: MigrationState) -> dict:
        import boto3

        plan = state["migration_plan"]
        stack_name = _stack_name_for(state)
        cfn = boto3.client("cloudformation", region_name=config.aws_region)
        overrides = state.get("param_overrides") or {}
        source_secret_values = state.get("source_secret_values") or {}
        source_name_candidates = list(state.get("source_vault_names") or [])
        if state.get("resource_group"):
            source_name_candidates.append(state["resource_group"])

        param_values: dict[str, str] = {}
        parameters = []
        carried_over: list[str] = []
        named_from_source: list[str] = []
        for name, definition in (plan.parameters or {}).items():
            value, source = _resolve_param_value(
                name, definition, overrides, source_secret_values, source_name_candidates
            )
            if value is None:
                msg = (
                    f"No value available for required parameter '{name}'. Supply one via "
                    f"--params-file, the CFN_PARAM_{name.upper()} environment variable, a matching "
                    "source Key Vault secret, or a template Default."
                )
                return {
                    "deploy_result": {"stack_name": stack_name, "status": "FAILED", "error": msg},
                    "agent_log": _log("agent6_deploy", "failed", msg),
                    "stopped": True,
                    "stop_reason": msg,
                }
            error = _validate_param_value(value, definition)
            if error is not None:
                msg = (
                    f"Parameter '{name}' value from {source} is invalid: {error}. Fix it via "
                    f"--params-file or the CFN_PARAM_{name.upper()} environment variable."
                )
                return {
                    "deploy_result": {"stack_name": stack_name, "status": "FAILED", "error": msg},
                    "agent_log": _log("agent6_deploy", "failed", msg),
                    "stopped": True,
                    "stop_reason": msg,
                }
            if source == "source-keyvault":
                carried_over.append(name)
            elif source == "source-name":
                named_from_source.append(name)
            param_values[name] = value
            parameters.append({"ParameterKey": name, "ParameterValue": value})

        template_body = state["cfn_yaml"]
        # stack_check_gate decides create vs. update ahead of time; fall back to a
        # fresh existence check if the gate was somehow skipped.
        action = state.get("stack_action") or ("update" if _stack_exists(cfn, stack_name) else "create")
        try:
            if action == "update":
                cfn.update_stack(
                    StackName=stack_name, TemplateBody=template_body, Parameters=parameters,
                    Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
                )
                waiter = cfn.get_waiter("stack_update_complete")
            else:
                cfn.create_stack(
                    StackName=stack_name, TemplateBody=template_body, Parameters=parameters,
                    Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
                )
                waiter = cfn.get_waiter("stack_create_complete")
            waiter.wait(StackName=stack_name)
        except Exception as exc:  # noqa: BLE001 - surfaced to report, not raised
            return {
                "deploy_result": {"stack_name": stack_name, "status": "FAILED", "error": str(exc)},
                "agent_log": _log("agent6_deploy", "failed", f"Deploy failed: {exc}"),
            }

        description = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
        deploy_result = {
            "stack_name": stack_name,
            "stack_id": description["StackId"],
            "status": description["StackStatus"],
        }

        verify_result = _verify_secrets(config, plan, param_values)
        message = f"Stack '{stack_name}' deployed with status {deploy_result['status']}."
        if carried_over:
            message += f" Carried over real values from the source Key Vault for: {', '.join(carried_over)}."
        if named_from_source:
            message += f" Used the source resource group/Key Vault name for: {', '.join(named_from_source)}."
        return {
            "deploy_result": deploy_result,
            "verify_result": verify_result,
            "agent_log": _log("agent6_deploy", "ok", message),
        }

    return agent6_deploy


def _stack_name_for(state: MigrationState) -> str:
    return f"migrated-{Path(state['bicep_path']).stem}"


def _resolve_param_value(
    name: str,
    definition: dict,
    overrides: dict[str, str],
    source_secret_values: dict[str, str],
    source_name_candidates: list[str],
) -> tuple[str | None, str]:
    """Resolve a CFN parameter value with no human input, in priority order:
    --params-file override, CFN_PARAM_<NAME> env var, a matching real value
    fetched from the source Key Vault (NoEcho params only), template Default
    (never for NoEcho/secret params), then -- for naming/prefix-style params
    only (e.g. 'SecretNamePrefix') with no Default -- the source resource
    group/Key Vault name. Returns (value, source); value is None when nothing
    could be resolved, which fails the run fast.
    """
    if name in overrides:
        return overrides[name], "params-file"
    env_value = os.environ.get(f"CFN_PARAM_{name.upper()}")
    if env_value is not None:
        return env_value, "environment"
    no_echo = bool(definition.get("NoEcho"))
    if no_echo:
        matched = _match_source_secret(name, source_secret_values)
        if matched is not None:
            return matched, "source-keyvault"
    default = definition.get("Default")
    if not no_echo and default is not None:
        return str(default), "template default"
    if not no_echo and source_name_candidates and _looks_like_name_prefix_param(name):
        return source_name_candidates[0], "source-name"
    return None, "missing"


_NAME_PREFIX_TOKENS = ("prefix", "namespace")


def _looks_like_name_prefix_param(name: str) -> bool:
    """Heuristic: does this parameter name look like a naming/prefix param
    (e.g. 'SecretNamePrefix'), as opposed to an arbitrary required value we
    can't safely guess (e.g. a KMS key ID)?
    """
    normalized = _normalize_key(name)
    return any(token in normalized for token in _NAME_PREFIX_TOKENS)


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _match_source_secret(name: str, source_secret_values: dict[str, str]) -> str | None:
    """Match a CFN parameter name to a fetched Key Vault secret by normalized
    name (case/hyphen/underscore-insensitive), e.g. 'DbPassword' <-> 'db-password'.
    """
    target = _normalize_key(name)
    for secret_name, value in source_secret_values.items():
        if _normalize_key(secret_name) == target:
            return value
    return None


def _validate_param_value(value: str, definition: dict) -> str | None:
    """Check a candidate parameter value against its CFN constraints client-side,
    so a bad value fails fast with a re-prompt instead of a wasted Create/UpdateStack
    call that can leave the stack in ROLLBACK_COMPLETE.
    """
    min_length = definition.get("MinLength")
    if min_length is not None and len(value) < int(min_length):
        return f"must be at least {min_length} character(s) long"
    max_length = definition.get("MaxLength")
    if max_length is not None and len(value) > int(max_length):
        return f"must be at most {max_length} character(s) long"
    pattern = definition.get("AllowedPattern")
    if pattern and re.fullmatch(pattern, value) is None:
        return f"must match pattern {pattern}"
    allowed_values = definition.get("AllowedValues")
    if allowed_values and value not in allowed_values:
        return f"must be one of {allowed_values}"
    return None


def _stack_exists(cfn, stack_name: str) -> bool:
    try:
        cfn.describe_stacks(StackName=stack_name)
        return True
    except Exception:
        return False


def _stack_status(cfn, stack_name: str) -> str | None:
    try:
        return cfn.describe_stacks(StackName=stack_name)["Stacks"][0]["StackStatus"]
    except Exception:
        return None


def _delete_stack_and_wait(cfn, stack_name: str) -> None:
    cfn.delete_stack(StackName=stack_name)
    cfn.get_waiter("stack_delete_complete").wait(StackName=stack_name)


# Stack statuses where CloudFormation refuses UpdateStack outright (e.g. the
# ROLLBACK_COMPLETE case seen after a failed create) -- must be deleted first.
_STACK_BLOCKS_UPDATE = {"ROLLBACK_COMPLETE", "CREATE_FAILED", "DELETE_FAILED"}


# ---------------------------------------------------------------------------
# Stack conflict gate: verify whether the target CFN stack already exists
# before agent6 mutates anything, and let the human choose update vs. delete.
# ---------------------------------------------------------------------------
def make_stack_check_gate(config: Config):
    def stack_check_gate(state: MigrationState) -> dict:
        import boto3

        stack_name = _stack_name_for(state)
        cfn = boto3.client("cloudformation", region_name=config.aws_region)
        status = _stack_status(cfn, stack_name)

        if status is None:
            return {
                "stack_action": "create",
                "agent_log": _log("stack_check_gate", "ok", f"No existing stack '{stack_name}' -- will create."),
            }

        if status.endswith("_IN_PROGRESS"):
            return {
                "stopped": True,
                "stop_reason": f"Stack '{stack_name}' has an operation in progress ({status}); try again later.",
                "agent_log": _log("stack_check_gate", "stopped", f"Stack busy ({status})."),
            }

        if status in _STACK_BLOCKS_UPDATE:
            print(f"\n[Stack check] Stack '{stack_name}' exists in state {status}, which cannot be updated.")
            answer = input("Delete this stack and recreate it? [y/N] ").strip().lower()
            if answer != "y":
                return {
                    "stopped": True,
                    "stop_reason": f"Human declined to delete stack '{stack_name}' stuck in {status}.",
                    "agent_log": _log("stack_check_gate", "stopped", f"Declined deletion of stack in {status}."),
                }
            _delete_stack_and_wait(cfn, stack_name)
            return {
                "stack_action": "create",
                "agent_log": _log(
                    "stack_check_gate", "ok", f"Deleted stack '{stack_name}' (was {status}); will recreate."
                ),
            }

        print(f"\n[Stack check] Stack '{stack_name}' already exists (status: {status}).")
        answer = input("Choose an action -- [U]pdate existing / [D]elete and recreate / [C]ancel: ").strip().lower()
        if answer == "u":
            return {
                "stack_action": "update",
                "agent_log": _log("stack_check_gate", "ok", f"Human chose to update existing stack '{stack_name}'."),
            }
        if answer == "d":
            _delete_stack_and_wait(cfn, stack_name)
            return {
                "stack_action": "create",
                "agent_log": _log(
                    "stack_check_gate", "ok", f"Human chose to delete and recreate stack '{stack_name}'."
                ),
            }
        return {
            "stopped": True,
            "stop_reason": f"Human cancelled deployment; stack '{stack_name}' already exists.",
            "agent_log": _log("stack_check_gate", "stopped", "Human cancelled at stack conflict gate."),
        }

    return stack_check_gate


def _verify_secrets(config: Config, plan, param_values: dict[str, str]) -> dict:
    """Smoke-test: confirm each planned SecretsManager secret exists (never reads value)."""
    import boto3

    secrets_client = boto3.client("secretsmanager", region_name=config.aws_region)
    checked = []
    for resource in plan.resources:
        if resource.aws_type != "AWS::SecretsManager::Secret":
            continue
        name = _resolve_name(resource.properties.get("Name"), param_values)
        try:
            if name is None:
                checked.append({"logical_id": resource.logical_id, "exists": "unknown (unresolvable name)"})
                continue
            secrets_client.describe_secret(SecretId=name)
            checked.append({"logical_id": resource.logical_id, "name": name, "exists": True})
        except Exception as exc:  # noqa: BLE001
            checked.append({"logical_id": resource.logical_id, "name": name, "exists": False, "error": str(exc)})
    return {"secrets_checked": checked}


def _resolve_name(name: Any, param_values: dict[str, str]) -> str | None:
    """Resolve a CFN `Name` property (plain string, Fn::Sub, or Ref) to its deployed value."""
    if isinstance(name, str):
        return name
    if not isinstance(name, dict):
        return None
    if "Fn::Sub" in name and isinstance(name["Fn::Sub"], str):
        return re.sub(r"\$\{(\w+)\}", lambda m: param_values.get(m.group(1), m.group(0)), name["Fn::Sub"])
    if "Ref" in name:
        return param_values.get(name["Ref"])
    return None


# ---------------------------------------------------------------------------
# Agent 7: write the migration report from the full graph state.
# ---------------------------------------------------------------------------
def make_agent7_report(reports_dir: Path):
    def agent7_report(state: MigrationState) -> dict:
        run_id = state["run_id"]
        run_dir = reports_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / "report.md"
        report_path.write_text(_render_report(state), encoding="utf-8")
        return {
            "report_path": str(report_path),
            "agent_log": _log("agent7_report", "ok", f"Report written to {report_path}."),
        }

    return agent7_report


def _render_report(state: MigrationState) -> str:
    lines = [
        f"# Migration report — run {state['run_id']}",
        "",
        f"- Generated: {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"- Bicep source: {state.get('bicep_path')}",
        f"- Overall status: {'STOPPED — ' + state['stop_reason'] if state.get('stopped') else 'COMPLETED'}",
        "",
        "## Agent log",
        "",
        "| Agent | Status | Message |",
        "|---|---|---|",
    ]
    for entry in state.get("agent_log", []):
        message = entry["message"].replace("\n", " ").replace("|", "\\|")[:300]
        lines.append(f"| {entry['agent']} | {entry['status']} | {message} |")

    lines += ["", "## Resource types", ""]
    lines.append(f"- Supported & processed: {', '.join(state.get('resource_types', [])) or '(none)'}")
    if state.get("unsupported_types"):
        lines.append(f"- Unsupported (skipped): {', '.join(state['unsupported_types'])}")

    if state.get("mapping_table"):
        lines += ["", "## Resource mapping (Agent 3)", "", "| Logical ID | Azure type | AWS type |", "|---|---|---|"]
        for m in state["mapping_table"]:
            lines.append(f"| {m['logical_id']} | {m['source_azure_type']} | {m['aws_type']} |")

    if "plan_confirmed" in state:
        lines += ["", "## Plan approval gate", "", f"- Human approved plan: {state['plan_confirmed']}"]

    if state.get("output_path"):
        lines += ["", "## Generated template (Agent 4)", "", f"- {state['output_path']}"]

    if state.get("validation_history"):
        max_attempts = state.get("max_fix_attempts", 2) + 1
        lines += [
            "",
            "## Validation (Agent 5)",
            "",
            "`cfn-lint` run against the rendered template before any real AWS call:",
            "",
        ]
        for entry in state["validation_history"]:
            result = "PASSED" if entry["passed"] else "FAILED"
            lines.append(
                f"- Attempt {entry['attempt']}/{max_attempts}: **{result}** "
                f"({entry['errors']} error(s), {entry['warnings']} warning(s))"
            )
            if not entry["passed"]:
                first_line = entry["output"].splitlines()[0] if entry["output"] else ""
                lines.append(f"  - {first_line}")
                lines.append("  - Fed back to Agent 3 (LLM) for a corrected migration plan.")
        lines.append("")
        lines.append("Full per-attempt output: `cfn_validation_report.txt` in this run's folder.")

    if state.get("deploy_result"):
        lines += ["", "## Deployment (Agent 6)", ""]
        for k, v in state["deploy_result"].items():
            lines.append(f"- {k}: {v}")

    if state.get("verify_result"):
        lines += ["", "## Post-deploy verification (Agent 6)", ""]
        for check in state["verify_result"].get("secrets_checked", []):
            lines.append(f"- {check}")

    return "\n".join(lines) + "\n"
