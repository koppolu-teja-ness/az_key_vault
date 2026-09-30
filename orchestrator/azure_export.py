"""Exports an existing Azure resource group as a .bicep file.

Uses `az group export` to pull the resource group's live ARM template, then
`az bicep decompile` to turn that ARM JSON into Bicep source. This lets the
migration pipeline start directly from a real Azure account instead of
requiring a hand-authored .bicep file.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .bicep_compiler import ensure_az_cli_available


class AzureExportError(RuntimeError):
    pass


def export_resource_group_to_bicep(
    resource_group: str, input_dir: Path, subscription_id: str | None = None
) -> Path:
    """Export `resource_group` from Azure and decompile it into a .bicep file
    under `input_dir`. Returns the path to the resulting .bicep file.
    """
    ensure_az_cli_available()
    input_dir.mkdir(parents=True, exist_ok=True)

    export_cmd = ["az", "group", "export", "--name", resource_group]
    if subscription_id:
        export_cmd += ["--subscription", subscription_id]
    result = subprocess.run(export_cmd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        raise AzureExportError(
            f"'az group export' failed for resource group '{resource_group}':\n{result.stderr}"
        )
    try:
        arm_template = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AzureExportError(
            f"Could not parse ARM JSON exported from resource group '{resource_group}': {exc}"
        ) from exc

    json_path = input_dir / f"{resource_group}.json"
    json_path.write_text(json.dumps(arm_template, indent=2), encoding="utf-8")

    decompile_cmd = ["az", "bicep", "decompile", "--file", str(json_path), "--force"]
    result = subprocess.run(decompile_cmd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        raise AzureExportError(
            f"'az bicep decompile' failed for '{json_path}':\n{result.stderr}"
        )

    bicep_path = json_path.with_suffix(".bicep")
    if not bicep_path.exists():
        raise AzureExportError(f"Expected decompiled Bicep file not found: {bicep_path}")
    return bicep_path


def fetch_resource_group_secret_values(
    resource_group: str, subscription_id: str | None = None
) -> tuple[dict[str, str], list[str], list[str]]:
    """Best-effort fetch of every Key Vault secret's real value in `resource_group`,
    keyed by secret name -- ARM/Bicep exports never carry secret values (Azure's
    control-plane export API omits them by design), so this reads them directly
    from each vault's data plane instead. Requires the az CLI identity to have
    secret-read access (e.g. "Key Vault Secrets User"); any failure is skipped
    rather than raised (a missing value just falls back further downstream),
    but is returned as a warning so the caller can surface it instead of the
    fetch silently doing nothing. Returns (secret_values, vault_names, warnings)
    -- vault_names lets the caller fall back to the source vault's own name for
    naming/prefix-style parameters that have no Default.
    """
    values: dict[str, str] = {}
    warnings: list[str] = []
    list_cmd = ["az", "keyvault", "list", "--resource-group", resource_group, "--query", "[].name", "-o", "tsv"]
    if subscription_id:
        list_cmd += ["--subscription", subscription_id]
    result = subprocess.run(list_cmd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        warnings.append(f"'az keyvault list' failed for resource group '{resource_group}': {result.stderr.strip()}")
        return values, [], warnings

    vault_names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    for vault_name in vault_names:
        list_secrets_cmd = [
            "az", "keyvault", "secret", "list", "--vault-name", vault_name, "--query", "[].name", "-o", "tsv",
        ]
        secrets_result = subprocess.run(list_secrets_cmd, capture_output=True, text=True, shell=True)
        if secrets_result.returncode != 0:
            warnings.append(f"Could not list secrets in vault '{vault_name}': {secrets_result.stderr.strip()}")
            continue
        for secret_name in (line.strip() for line in secrets_result.stdout.splitlines() if line.strip()):
            show_cmd = [
                "az", "keyvault", "secret", "show", "--vault-name", vault_name, "--name", secret_name,
                "--query", "value", "-o", "tsv",
            ]
            show_result = subprocess.run(show_cmd, capture_output=True, text=True, shell=True)
            if show_result.returncode == 0 and show_result.stdout.strip():
                values[secret_name] = show_result.stdout.strip()
            else:
                warnings.append(f"Could not read secret '{secret_name}' in vault '{vault_name}': {show_result.stderr.strip()}")
    return values, vault_names, warnings
