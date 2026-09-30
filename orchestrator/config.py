"""Runtime configuration, sourced from environment variables / a local .env file.

No secrets are hard-coded here. AZURE_RESOURCE_GROUP / AZURE_SUBSCRIPTION_ID are
read from .env (never from CLI flags) so they never end up in shell history or
process argv listings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    aws_region: str
    bedrock_model_id: str
    max_fix_attempts: int
    azure_resource_group: str | None
    azure_subscription_id: str | None

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            aws_region=os.environ.get("AWS_REGION", "us-east-1"),
            bedrock_model_id=os.environ.get(
                "BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0"
            ),
            max_fix_attempts=int(os.environ.get("MAX_FIX_ATTEMPTS", "2")),
            azure_resource_group=os.environ.get("AZURE_RESOURCE_GROUP") or None,
            azure_subscription_id=os.environ.get("AZURE_SUBSCRIPTION_ID") or None,
        )
