"""LangGraph wiring for the 7-agent Bicep -> CloudFormation migration pipeline.

Graph shape:

    agent1_validate --stop--> agent7_report --> END
                    --continue--> agent2_build_cnr --> agent3_map_resources
                    --> plan_approval_gate
                        --rejected--> agent7_report --> END
                        --approved--> agent4_render --> agent5_validate_cfn
                            --retry (lint fail, attempts left)--> agent3_map_resources
                            --give up (lint fail, attempts exhausted)--> agent7_report --> END
                            --pass--> deploy_gate
                                        --declined--> agent7_report --> END
                                        --approved--> stack_check_gate
                                            --cancelled/blocked--> agent7_report --> END
                                            --ok--> agent6_deploy --> agent7_report --> END

Agents 1, 2, 4, 5 are deterministic wrappers around existing orchestrator
modules; only agent3 (mapping) calls the LLM. plan_approval_gate is a
mandatory human sign-off on the migration plan before any CloudFormation is
generated; deploy_gate is a mandatory human-confirmation checkpoint before
agent6 performs any real AWS mutation. stack_check_gate looks up the target
CFN stack right before deployment and, if it already exists, asks the human
to update it in place or delete-and-recreate it (auto-detecting unrecoverable
states like ROLLBACK_COMPLETE that CloudFormation refuses to update).
"""
from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, StateGraph

from .agents import (
    agent2_build_cnr,
    agent5_validate_cfn,
    deploy_gate,
    make_agent1_validate,
    make_agent3_map_resources,
    make_agent4_render,
    make_agent6_deploy,
    make_agent7_report,
    make_stack_check_gate,
    plan_approval_gate,
)
from .config import Config
from .generator import Generator
from .knowledge_base import KnowledgeBase
from .state import MigrationState


def _route_after_validate(state: MigrationState) -> str:
    if state.get("stopped"):
        return "report"
    if state.get("dry_run"):
        return "report"
    return "continue"


def _route_after_lint(state: MigrationState) -> str:
    if state.get("lint_passed"):
        return "deploy_gate"
    if state.get("fix_attempts", 0) < state.get("max_fix_attempts", 2):
        return "retry"
    return "report"


def _route_after_plan_gate(state: MigrationState) -> str:
    return "render" if state.get("plan_confirmed") else "report"


def _route_after_gate(state: MigrationState) -> str:
    return "deploy" if state.get("deploy_confirmed") else "report"


def _route_after_stack_check(state: MigrationState) -> str:
    return "report" if state.get("stopped") else "deploy"


def _bump_fix_attempts(state: MigrationState) -> dict:
    return {"fix_attempts": state.get("fix_attempts", 0) + 1}


def _lint_give_up(state: MigrationState) -> dict:
    attempts = state.get("fix_attempts", 0) + 1
    reason = f"cfn-lint still failing after {attempts} attempt(s); stopping before deployment."
    return {
        "stopped": True,
        "stop_reason": reason,
        "agent_log": [{"agent": "agent5_validate_cfn", "status": "stopped", "message": reason}],
    }


def build_graph(
    knowledge_base: KnowledgeBase,
    generator: Generator,
    config: Config,
    output_dir: Path,
    reports_dir: Path,
):
    graph = StateGraph(MigrationState)

    graph.add_node("agent1_validate", make_agent1_validate(knowledge_base))
    graph.add_node("agent2_build_cnr", agent2_build_cnr)
    graph.add_node("agent3_map_resources", make_agent3_map_resources(knowledge_base, generator))
    graph.add_node("plan_approval_gate", plan_approval_gate)
    graph.add_node("agent4_render", make_agent4_render(output_dir))
    graph.add_node("agent5_validate_cfn", agent5_validate_cfn)
    graph.add_node("bump_fix_attempts", _bump_fix_attempts)
    graph.add_node("lint_give_up", _lint_give_up)
    graph.add_node("deploy_gate", deploy_gate)
    graph.add_node("stack_check_gate", make_stack_check_gate(config))
    graph.add_node("agent6_deploy", make_agent6_deploy(config))
    graph.add_node("agent7_report", make_agent7_report(reports_dir))

    graph.set_entry_point("agent1_validate")

    graph.add_conditional_edges(
        "agent1_validate", _route_after_validate, {"report": "agent7_report", "continue": "agent2_build_cnr"}
    )
    graph.add_edge("agent2_build_cnr", "agent3_map_resources")
    graph.add_edge("agent3_map_resources", "plan_approval_gate")
    graph.add_conditional_edges(
        "plan_approval_gate", _route_after_plan_gate, {"render": "agent4_render", "report": "agent7_report"}
    )
    graph.add_edge("agent4_render", "agent5_validate_cfn")
    graph.add_conditional_edges(
        "agent5_validate_cfn",
        _route_after_lint,
        {"retry": "bump_fix_attempts", "deploy_gate": "deploy_gate", "report": "lint_give_up"},
    )
    graph.add_edge("bump_fix_attempts", "agent3_map_resources")
    graph.add_edge("lint_give_up", "agent7_report")
    graph.add_conditional_edges(
        "deploy_gate", _route_after_gate, {"deploy": "stack_check_gate", "report": "agent7_report"}
    )
    graph.add_conditional_edges(
        "stack_check_gate", _route_after_stack_check, {"deploy": "agent6_deploy", "report": "agent7_report"}
    )
    graph.add_edge("agent6_deploy", "agent7_report")
    graph.add_edge("agent7_report", END)

    return graph.compile()
