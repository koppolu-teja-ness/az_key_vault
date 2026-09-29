# Migration report — run b8047bdd

- Generated: 2026-09-29T12:22:08
- Bicep source: keyvault.bicep
- Overall status: STOPPED — Human rejected the migration plan at the plan approval gate.

## Agent log

| Agent | Status | Message |
|---|---|---|
| agent1_validate | ok | All 2 resource type(s) supported. |
| agent2_build_cnr | ok | Built cloud-neutral templates for 3 resource(s). |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| plan_approval_gate | stopped | Human rejected the migration plan. |

## Resource types

- Supported & processed: Microsoft.KeyVault/vaults, Microsoft.KeyVault/vaults/secrets

## Resource mapping (Agent 3)

| Logical ID | Azure type | AWS type |
|---|---|---|
| DbUsernameSecret | Microsoft.KeyVault/vaults/secrets | AWS::SecretsManager::Secret |
| DbPasswordSecret | Microsoft.KeyVault/vaults/secrets | AWS::SecretsManager::Secret |

## Plan approval gate

- Human approved plan: False
