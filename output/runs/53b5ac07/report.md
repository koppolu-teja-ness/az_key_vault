# Migration report — run 53b5ac07

- Generated: 2026-09-29T12:42:21
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
| agent5_validate_cfn | warning | W1030 {'Ref': 'DbUsername'} is shorter than 1 when 'Ref' is resolved C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml:24:9  W1030 {'Ref': 'DbPassword'} is shorter than 1 when 'Ref' is resolved C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.g |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| plan_approval_gate | ok | Human approved the migration plan. |
| agent4_render | ok | Rendered CloudFormation template to C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml. |
| agent5_validate_cfn | warning | E2015 Default should have a length above or equal to MinLength C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml:11:5  E2015 Default should have a length above or equal to MinLength C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yam |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| plan_approval_gate | ok | Human approved the migration plan. |
| agent4_render | ok | Rendered CloudFormation template to C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml. |
| agent5_validate_cfn | ok | cfn-lint passed. |
| deploy_gate | ok | Human approved deployment. |
| stack_check_gate | ok | Deleted stack 'migrated-keyvault' (was ROLLBACK_COMPLETE); will recreate. |
| agent6_deploy | failed | Deploy failed: An error occurred (ValidationError) when calling the CreateStack operation: Parameter 'DbUsername' must match pattern [a-zA-Z0-9]* |

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
- error: An error occurred (ValidationError) when calling the CreateStack operation: Parameter 'DbUsername' must match pattern [a-zA-Z0-9]*
