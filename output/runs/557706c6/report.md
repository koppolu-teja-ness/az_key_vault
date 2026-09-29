# Migration report — run 557706c6

- Generated: 2026-09-29T12:32:23
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
| agent5_validate_cfn | warning | W1030 {'Ref': 'DbUsername'} is shorter than 1 when 'Ref' is resolved C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml:36:9  W1030 {'Ref': 'DbPassword'} is shorter than 1 when 'Ref' is resolved C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.g |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| plan_approval_gate | ok | Human approved the migration plan. |
| agent4_render | ok | Rendered CloudFormation template to C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml. |
| agent5_validate_cfn | warning | E2015 Default should have a length above or equal to MinLength C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml:11:5  E2015 Default should have a length above or equal to MinLength C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yam |

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

- cfn-lint passed: False
