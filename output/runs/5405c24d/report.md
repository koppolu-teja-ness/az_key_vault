# Migration report — run 5405c24d

- Generated: 2026-09-29T14:31:44
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
| agent5_validate_cfn | warning | E1020 'KmsKeyId' is not one of ['SecretNamePrefix', 'DbUsername', 'DbPassword', 'AWS::AccountId', 'AWS::NoValue', 'AWS::NotificationARNs', 'AWS::Partition', 'AWS::Region', 'AWS::StackId', 'AWS::StackName', 'AWS::URLSuffix'] C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.genera |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| plan_approval_gate | ok | Human approved the migration plan. |
| agent4_render | ok | Rendered CloudFormation template to C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml. |
| agent5_validate_cfn | warning | W1030 {'Ref': 'DbUsername'} is shorter than 1 when 'Ref' is resolved C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml:34:9  W1030 {'Ref': 'DbPassword'} is shorter than 1 when 'Ref' is resolved C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.g |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| plan_approval_gate | ok | Human approved the migration plan. |
| agent4_render | ok | Rendered CloudFormation template to C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml. |
| agent5_validate_cfn | ok | cfn-lint passed. |
| deploy_gate | ok | Human approved deployment. |
| stack_check_gate | ok | Deleted stack 'migrated-keyvault' (was ROLLBACK_COMPLETE); will recreate. |
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
- stack_id: arn:aws:cloudformation:us-east-1:590183679875:stack/migrated-keyvault/50eb46d0-bbe4-11f1-9e8f-0afff8ef0f95
- status: CREATE_COMPLETE

## Post-deploy verification (Agent 6)

- {'logical_id': 'DbUsernameSecret', 'name': 'myapp/db-username', 'exists': True}
- {'logical_id': 'DbPasswordSecret', 'name': 'myapp/db-password', 'exists': True}
