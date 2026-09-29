# Migration report — run 0f6d7fa3

- Generated: 2026-09-29T12:25:47
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
| agent5_validate_cfn | warning | E2015 Default should be allowed by AllowedPattern C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml:7:5  E2015 Default should have a length above or equal to MinLength C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml:7:5   |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| plan_approval_gate | ok | Human approved the migration plan. |
| agent4_render | ok | Rendered CloudFormation template to C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml. |
| agent5_validate_cfn | ok | cfn-lint passed. |
| deploy_gate | ok | Human approved deployment. |
| agent6_deploy | failed | Deploy failed: An error occurred (ValidationError) when calling the UpdateStack operation: Stack:arn:aws:cloudformation:us-east-1:590183679875:stack/migrated-keyvault/70543890-bbd2-11f1-9a6c-0e03a62e0e19 is in ROLLBACK_COMPLETE state and can not be updated. |

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
- status: FAILED
- error: An error occurred (ValidationError) when calling the UpdateStack operation: Stack:arn:aws:cloudformation:us-east-1:590183679875:stack/migrated-keyvault/70543890-bbd2-11f1-9a6c-0e03a62e0e19 is in ROLLBACK_COMPLETE state and can not be updated.
