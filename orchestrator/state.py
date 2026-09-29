"""Shared state passed between the 7 migration agents in orchestrator/graph.py.

One TypedDict flows through every LangGraph node; each agent reads what it
needs and returns a partial dict of updates (LangGraph merges these into the
running state). `agent_log` is additive (each agent appends one entry) so
Agent 7 can build a report from the full history without re-deriving it.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentLogEntry(TypedDict):
    agent: str
    status: str  # "ok" | "warning" | "stopped" | "failed"
    message: str


class MigrationState(TypedDict, total=False):
    # Inputs
    bicep_path: str
    output_dir: str
    run_id: str
    dry_run: bool

    # Agent 1: validate
    arm_template: dict[str, Any]
    resource_types: list[str]
    supported_types: list[str]
    unsupported_types: list[str]
    agent1_decision: str  # "auto_continue" | "human_approved" | "stopped"
    stopped: bool
    stop_reason: str

    # Agent 2: cloud-neutral representation
    cnr: Any  # orchestrator.cloud_neutral.CloudNeutralRepresentation
    per_resource_templates: dict[str, dict]  # logical_id -> custom template

    # Agent 3: mapping / migration plan (LLM reasoning)
    mapping_docs: dict[str, str]
    migration_plan_raw: str
    migration_plan: Any  # orchestrator.migration_plan.MigrationPlan
    mapping_table: list[dict]  # [{logical_id, source_azure_type, aws_type}]

    # Plan approval gate: mandatory human sign-off before CFN generation
    plan_confirmed: bool

    # Agent 4: render
    cfn_yaml: str
    output_path: str

    # Agent 5: validate rendered template
    lint_passed: bool
    lint_output: str
    fix_attempts: int
    max_fix_attempts: int

    # Deploy gate + stack conflict gate + Agent 6: deploy
    deploy_confirmed: bool
    stack_action: str  # "create" | "update" (decided by stack_check_gate)
    deploy_result: dict
    verify_result: dict

    # Agent 7: report
    report_path: str
    agent_log: Annotated[list[AgentLogEntry], operator.add]
