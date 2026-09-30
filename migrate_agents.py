#!/usr/bin/env python
"""CLI entrypoint for the 7-agent Bicep -> CloudFormation migration graph.

    Agent 0  export_resource_group  (optional) az group export + bicep decompile -> input/<rg>.bicep
    Agent 1  validate_bicep       compile + resource-support check, continue/stop
    Agent 2  build_cnr            cloud-neutral representation, per-resource templates
    Agent 3  map_resources        LLM: resource -> AWS-equivalent mapping (migration plan)
    -        plan_approval_gate   human review/approval of the migration plan
    Agent 4  render_cfn           deterministic plan -> CloudFormation YAML
    Agent 5  validate_cfn         cfn-lint, retries Agent 3 on failure
    -        stack_check_gate     human confirms update/delete/cancel for an existing target stack
    Agent 6  deploy                boto3 create/update-stack + post-deploy verification (fully
                                   automatic -- no confirmation prompt, no interactive parameter
                                   entry; see --params-file / CFN_PARAM_<NAME> below)
    Agent 7  report               writes output/runs/<run_id>/report.md

Example:
    python migrate_agents.py keyvault.bicep
    python migrate_agents.py keyvault.bicep --dry-run
    python migrate_agents.py keyvault.bicep --params-file params.json
    python migrate_agents.py   # exports AZURE_RESOURCE_GROUP from .env instead

CFN template parameters are resolved with no human input, in priority order:
1. --params-file (a flat JSON object of {"ParamName": "value"})
2. a CFN_PARAM_<NAME> environment variable (e.g. CFN_PARAM_ADMINUSERNAME)
3. for NoEcho/secret parameters only, a matching real value fetched from the
   source Key Vault (Agent 0's resource-group export flow only)
4. the template's own Default (never used for NoEcho/secret parameters)
Anything else unresolved, or invalid against the parameter's own constraints
(MinLength/MaxLength/AllowedPattern/AllowedValues), stops the run with a
clear error instead of blocking on a prompt.

AZURE_RESOURCE_GROUP / AZURE_SUBSCRIPTION_ID (Agent 0's export source) are read
from a local .env file / the environment -- never from CLI flags -- so they
never appear in shell history or process argv listings.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from orchestrator.config import Config
from orchestrator.generator import BedrockGenerator, GeneratorNotConfiguredError
from orchestrator.graph import build_graph
from orchestrator.knowledge_base import KnowledgeBase

REPO_ROOT = Path(__file__).parent
DEFAULT_KB_INDEX = REPO_ROOT / "knowledge_base" / "index.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "bicep_file", type=Path, nargs="?", default=None,
        help="Path to the .bicep source file (omit to use AZURE_RESOURCE_GROUP from .env instead)",
    )
    parser.add_argument("--input-dir", type=Path, default=REPO_ROOT / "input")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "output")
    parser.add_argument("--kb-index", type=Path, default=DEFAULT_KB_INDEX)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run only Agent 1 (validate) + write a report; skip LLM/render/deploy.",
    )
    parser.add_argument(
        "--params-file", type=Path, default=None,
        help="JSON file of {ParamName: value} for CFN template parameters (non-interactive deploy).",
    )
    args = parser.parse_args()

    config = Config.from_env()

    if not args.bicep_file and not config.azure_resource_group:
        parser.error("pass bicep_file, or set AZURE_RESOURCE_GROUP in .env")
    if args.bicep_file and config.azure_resource_group:
        parser.error("pass either bicep_file or AZURE_RESOURCE_GROUP in .env, not both")

    param_overrides = {}
    if args.params_file:
        try:
            param_overrides = json.loads(args.params_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"--params-file {args.params_file}: {exc}")
        if not isinstance(param_overrides, dict) or not all(isinstance(v, str) for v in param_overrides.values()):
            parser.error("--params-file must be a flat JSON object of {ParamName: \"value\"} strings")

    knowledge_base = KnowledgeBase(args.kb_index)

    generator = None
    if not args.dry_run:
        try:
            generator = BedrockGenerator(config)
        except GeneratorNotConfiguredError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print("hint: pass --dry-run to validate without a generator.", file=sys.stderr)
            return 1

    reports_dir = args.output_dir / "runs"
    app = build_graph(knowledge_base, generator, config, args.output_dir, reports_dir, args.input_dir)

    initial_state = {
        "output_dir": str(args.output_dir),
        "run_id": uuid.uuid4().hex[:8],
        "dry_run": args.dry_run,
        "fix_attempts": 0,
        "max_fix_attempts": config.max_fix_attempts,
        "param_overrides": param_overrides,
        "agent_log": [],
    }
    if args.bicep_file:
        initial_state["bicep_path"] = str(args.bicep_file)
    else:
        initial_state["resource_group"] = config.azure_resource_group
        initial_state["subscription_id"] = config.azure_subscription_id

    final_state = app.invoke(initial_state, config={"recursion_limit": 50})

    print(f"\nReport: {final_state.get('report_path')}")
    if final_state.get("stopped"):
        print(f"Stopped: {final_state.get('stop_reason')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
