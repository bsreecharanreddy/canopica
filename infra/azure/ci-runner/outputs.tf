output "resource_group_name" {
  description = "Pass to ci.yml's start-runner/stop-runner az vm start/deallocate commands."
  value       = azurerm_resource_group.this.name
}

output "vm_name" {
  description = "Pass to ci.yml's start-runner/stop-runner az vm start/deallocate commands."
  value       = azurerm_linux_virtual_machine.this.name
}

output "azure_client_id" {
  description = "Set as the AZURE_CLIENT_ID repo variable (Settings -> Secrets and variables -> Actions -> Variables) -- not a secret, no client secret exists with OIDC federation."
  value       = azuread_application.ci_runner.client_id
}

output "azure_tenant_id" {
  description = "Set as the AZURE_TENANT_ID repo variable."
  value       = data.azurerm_client_config.current.tenant_id
}

output "azure_subscription_id" {
  description = "Set as the AZURE_SUBSCRIPTION_ID repo variable."
  value       = data.azurerm_client_config.current.subscription_id
}

output "one_time_registration_command" {
  description = "Run this once, after 'terraform apply' and after cloud-init has finished (a few minutes), to register the runner. Needs a fresh registration token first -- see README.md step 4."
  value       = <<-EOT
    az vm run-command invoke \
      --resource-group ${azurerm_resource_group.this.name} \
      --name ${azurerm_linux_virtual_machine.this.name} \
      --command-id RunShellScript \
      --scripts "cd /opt/actions-runner && sudo -u ${var.admin_username} ./config.sh --url https://github.com/${var.github_repository} --token <REGISTRATION_TOKEN> --labels canopica-heavy --unattended --replace && ./svc.sh install ${var.admin_username} && ./svc.sh start"
  EOT
}
