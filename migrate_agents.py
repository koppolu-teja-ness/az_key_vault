#!/usr/bin/env python
"""CLI entrypoint for the 7-agent Bicep -> CloudFormation migration graph.

    Agent 1  validate_bicep       compile + resource-support check, continue/stop
    Agent 2  build_cnr            cloud-neutral representation, per-resource templates
    Agent 3  map_resources        LLM: resource -> AWS-equivalent mapping (migration plan)
    -        plan_approval_gate   human review/approval of the migration plan
    Agent 4  render_cfn           deterministic plan -> CloudFormation YAML
    Agent 5  validate_cfn         cfn-lint, retries Agent 3 on failure
    Agent 6  deploy               boto3 create/update-stack + post-deploy verification
    Agent 7  report               writes output/runs/<run_id>/report.md

Example:
    python migrate_agents.py keyvault.bicep
    python migrate_agents.py keyvault.bicep --dry-run
"""
from __future__ import annotations

import argparse
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
    parser.add_argument("bicep_file", type=Path, help="Path to the .bicep source file")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "output")
    parser.add_argument("--kb-index", type=Path, default=DEFAULT_KB_INDEX)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run only Agent 1 (validate) + write a report; skip LLM/render/deploy.",
    )
    args = parser.parse_args()

    config = Config.from_env()
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
    app = build_graph(knowledge_base, generator, config, args.output_dir, reports_dir)

    initial_state = {
        "bicep_path": str(args.bicep_file),
        "output_dir": str(args.output_dir),
        "run_id": uuid.uuid4().hex[:8],
        "dry_run": args.dry_run,
        "fix_attempts": 0,
        "max_fix_attempts": config.max_fix_attempts,
        "agent_log": [],
    }

    final_state = app.invoke(initial_state, config={"recursion_limit": 50})

    print(f"\nReport: {final_state.get('report_path')}")
    if final_state.get("stopped"):
        print(f"Stopped: {final_state.get('stop_reason')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
