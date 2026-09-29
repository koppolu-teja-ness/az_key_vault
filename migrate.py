#!/usr/bin/env python
"""CLI entrypoint for the Azure Bicep -> AWS CloudFormation migration pipeline.

Examples:
    # Check parsing + knowledge-base coverage without calling any LLM/API
    python migrate.py main.bicep --dry-run

    # Full run (requires AWS Bedrock credentials)
    python migrate.py main.bicep --output-dir output
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from orchestrator.bicep_compiler import BicepCompilerError
from orchestrator.config import Config
from orchestrator.generator import BedrockGenerator, GeneratorNotConfiguredError
from orchestrator.knowledge_base import KnowledgeBase
from orchestrator.migration_plan import MigrationPlanError
from orchestrator.pipeline import UnmappedResourceError, run_pipeline

REPO_ROOT = Path(__file__).parent
DEFAULT_KB_INDEX = REPO_ROOT / "knowledge_base" / "index.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bicep_file", type=Path, help="Path to the .bicep source file")
    parser.add_argument(
        "--output-dir", type=Path, default=REPO_ROOT / "output",
        help="Directory to write the generated CFN YAML into",
    )
    parser.add_argument(
        "--kb-index", type=Path, default=DEFAULT_KB_INDEX,
        help="Path to the knowledge base index.json",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only compile + check knowledge-base coverage, skip generation/LLM calls",
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
            print("hint: pass --dry-run to test parsing without a generator.", file=sys.stderr)
            return 1

    try:
        result = run_pipeline(
            bicep_path=args.bicep_file,
            output_dir=args.output_dir,
            knowledge_base=knowledge_base,
            generator=generator,
            config=config,
            dry_run=args.dry_run,
        )
    except (BicepCompilerError, UnmappedResourceError, GeneratorNotConfiguredError, MigrationPlanError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Resource types found: {', '.join(result.resource_types)}")
    if args.dry_run:
        print("Dry run OK: all resource types have knowledge-base mappings.")
        return 0

    print(f"Generated template: {result.output_path}")
    print(f"cfn-lint passed: {result.lint_passed}")
    if not result.lint_passed:
        print(result.lint_output, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
