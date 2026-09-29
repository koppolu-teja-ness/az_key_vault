# Migration report — run 0381b085

- Generated: 2026-09-29T12:08:03
- Bicep source: keyvault.bicep
- Overall status: COMPLETED

## Agent log

| Agent | Status | Message |
|---|---|---|
| agent1_validate | ok | All 2 resource type(s) supported. |
| agent2_build_cnr | ok | Built cloud-neutral templates for 3 resource(s). |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| agent4_render | ok | Rendered CloudFormation template to C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml. |
| agent5_validate_cfn | warning | W1030 {'Ref': 'DbUsername'} is shorter than 1 when 'Ref' is resolved C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml:24:9  W1030 {'Ref': 'DbPassword'} is shorter than 1 when 'Ref' is resolved C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.g |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| agent4_render | ok | Rendered CloudFormation template to C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml. |
| agent5_validate_cfn | warning | E2015 Default should have a length above or equal to MinLength C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml:10:5  E2015 Default should have a length above or equal to MinLength C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yam |
| agent3_map_resources | ok | Mapped 2 resource(s) to AWS equivalents. |
| agent4_render | ok | Rendered CloudFormation template to C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml. |
| agent5_validate_cfn | ok | cfn-lint passed. |
| deploy_gate | ok | Human approved deployment. |
| agent6_deploy | ok | Stack 'migrated-keyvault' deployed with status CREATE_COMPLETE. |

## Resource types

- Supported & processed: Microsoft.KeyVault/vaults, Microsoft.KeyVault/vaults/secrets

## Resource mapping (Agent 3)

| Logical ID | Azure type | AWS type |
|---|---|---|
| DbUsernameSecret | Microsoft.KeyVault/vaults/secrets | AWS::SecretsManager::Secret |
| DbPasswordSecret | Microsoft.KeyVault/vaults/secrets | AWS::SecretsManager::Secret |

## Generated template (Agent 4)

- C:\Charan_workspace\azure_workspace-main\az_key_vault\output\keyvault.generated.yaml

## Validation (Agent 5)

- cfn-lint passed: True

## Deployment (Agent 6)

- stack_name: migrated-keyvault
- stack_id: arn:aws:cloudformation:us-east-1:590183679875:stack/migrated-keyvault/3d67f1d0-bbd0-11f1-b0a8-0afff64fb7bb
- status: CREATE_COMPLETE

## Post-deploy verification (Agent 6)

- {'logical_id': 'DbUsernameSecret', 'exists': 'unknown (dynamic name)'}
- {'logical_id': 'DbPasswordSecret', 'exists': 'unknown (dynamic name)'}
