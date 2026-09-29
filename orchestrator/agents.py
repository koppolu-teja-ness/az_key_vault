"""The 7 migration agents, each a thin, testable function over MigrationState.

Deterministic stages (1, 2, 4, 5) wrap existing orchestrator modules unchanged;
only Agent 3 (mapping) calls the LLM. This keeps the same "LLM only reasons,
never emits template syntax" split as pipeline.py, just organized as discrete
agents instead of one linear function.
"""
from __future__ import annotations

import dataclasses
import datetime
import getpass
import re
from pathlib import Path
from typing import Any

from .bicep_compiler import BicepCompilerError, compile_bicep_to_arm
from .cfn_generator import generate_cloudformation
from .cloud_neutral import build_cnr
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
def agent5_validate_cfn(state: MigrationState) -> dict:
    lint_passed, lint_output = run_cfn_lint(Path(state["output_path"]))
    status = "ok" if lint_passed else "warning"
    return {
        "lint_passed": lint_passed,
        "lint_output": lint_output,
        "agent_log": _log("agent5_validate_cfn", status, "cfn-lint passed." if lint_passed else lint_output),
    }


# ---------------------------------------------------------------------------
# Agent 6: deploy the validated template to AWS and verify it (real deploy).
# ---------------------------------------------------------------------------
def make_agent6_deploy(config: Config):
    def agent6_deploy(state: MigrationState) -> dict:
        import boto3

        plan = state["migration_plan"]
        stack_name = _stack_name_for(state)
        cfn = boto3.client("cloudformation", region_name=config.aws_region)

        param_values: dict[str, str] = {}
        parameters = []
        for name, definition in (plan.parameters or {}).items():
            no_echo = bool(definition.get("NoEcho"))
            default = definition.get("Default")
            while True:
                if no_echo:
                    # Secure params are always entered fresh -- never reuse a template Default.
                    value = getpass.getpass(f"Value for secure parameter '{name}': ")
                elif default not in (None, ""):
                    value = str(default)
                else:
                    value = input(f"Value for parameter '{name}': ")
                error = _validate_param_value(value, definition)
                if error is None:
                    break
                print(f"Invalid value for '{name}': {error}. Please re-enter.")
                default = None  # a bad Default must not be silently reused on retry
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
        return {
            "deploy_result": deploy_result,
            "verify_result": verify_result,
            "agent_log": _log(
                "agent6_deploy", "ok", f"Stack '{stack_name}' deployed with status {deploy_result['status']}."
            ),
        }

    return agent6_deploy


def _stack_name_for(state: MigrationState) -> str:
    return f"migrated-{Path(state['bicep_path']).stem}"


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
# Deploy gate: mandatory human confirmation before any AWS mutation.
# ---------------------------------------------------------------------------
def deploy_gate(state: MigrationState) -> dict:
    print(f"\n[Deploy gate] About to deploy '{state['output_path']}' to AWS region.")
    answer = input("Proceed with real AWS deployment? [y/N] ").strip().lower()
    confirmed = answer == "y"
    update = {
        "deploy_confirmed": confirmed,
        "agent_log": _log(
            "deploy_gate", "ok" if confirmed else "stopped",
            "Human approved deployment." if confirmed else "Human declined deployment.",
        ),
    }
    if not confirmed:
        update["stopped"] = True
        update["stop_reason"] = "Human declined deployment at the deploy gate."
    return update


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

    if "lint_passed" in state:
        lines += ["", "## Validation (Agent 5)", "", f"- cfn-lint passed: {state['lint_passed']}"]

    if state.get("deploy_result"):
        lines += ["", "## Deployment (Agent 6)", ""]
        for k, v in state["deploy_result"].items():
            lines.append(f"- {k}: {v}")

    if state.get("verify_result"):
        lines += ["", "## Post-deploy verification (Agent 6)", ""]
        for check in state["verify_result"].get("secrets_checked", []):
            lines.append(f"- {check}")

    return "\n".join(lines) + "\n"
