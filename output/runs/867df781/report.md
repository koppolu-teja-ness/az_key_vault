# Migration report — run 867df781

- Generated: 2026-09-29T12:53:53
- Bicep source: keyvault.bicep
- Overall status: COMPLETED

## Agent log

| Agent | Status | Message |
|---|---|---|
| agent1_validate | ok | All 2 resource type(s) supported. |
| agent2_build_cnr | ok | Built cloud-neutral templates for 3 resource(s). |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| plan_approval_gate | ok | Human approved the migration plan. |
| agent4_render | ok | Rendered CloudFormation template to C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml. |
| agent5_validate_cfn | ok | cfn-lint passed. |
| deploy_gate | ok | Human approved deployment. |
| stack_check_gate | ok | No existing stack 'migrated-keyvault' -- will create. |
| agent6_deploy | ok | Stack 'migrated-keyvault' deployed with status CREATE_COMPLETE. |

## Resource types

- Supported & processed: Microsoft.KeyVault/vaults, Microsoft.KeyVault/vaults/secrets

## Resource mapping (Agent 3)

| Logical ID | Azure type | AWS type |
|---|---|---|
| DbUsernameSecret | Microsoft.KeyVault/vaults/secrets | AWS::SecretsManager::Secret |
| DbPasswordSecret | Microsoft.KeyVault/vaults/secrets | AWS::SecretsManager::Secret |

## Plan approval gate

- Human approved plan: True

## Generated template (Agent 4)

- C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml

## Validation (Agent 5)

- cfn-lint passed: True

## Deployment (Agent 6)

- stack_name: migrated-keyvault
- stack_id: arn:aws:cloudformation:us-east-1:590183679875:stack/migrated-keyvault/1c9c4eb0-bbd5-11f1-9eeb-0e5c342297f7
- status: CREATE_COMPLETE

## Post-deploy verification (Agent 6)

- {'logical_id': 'DbUsernameSecret', 'name': 'myapp/prod/db-username', 'exists': True}
- {'logical_id': 'DbPasswordSecret', 'name': 'myapp/prod/db-password', 'exists': True}
