"""Runtime configuration, sourced from environment variables.

No secrets are hard-coded here; set these in your shell or a local .env
(loaded by direnv/dotenv if you add that later) before running migrate.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    aws_region: str
    bedrock_model_id: str
    max_fix_attempts: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            aws_region=os.environ.get("AWS_REGION", "us-east-1"),
            bedrock_model_id=os.environ.get(
                "BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0"
            ),
            max_fix_attempts=int(os.environ.get("MAX_FIX_ATTEMPTS", "2")),
        )
