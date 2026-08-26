output "resource_group_name" {
  description = "Name of the resource group holding every resource in this configuration."
  value       = azurerm_resource_group.this.name
}

output "postgres_fqdn" {
  description = "FQDN of the Postgres Flexible Server (holds the canopica_operational, canopica_serving, and airflow databases)."
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

output "key_vault_uri" {
  description = "URI of the Key Vault holding the generated Postgres admin password."
  value       = azurerm_key_vault.this.vault_uri
}

output "container_registry_login_server" {
  description = "Login server for the Container Registry -- push api_image/ui_image/airflow_image here before applying."
  value       = azurerm_container_registry.this.login_server
}

output "api_url" {
  description = "Public HTTPS FQDN of the API Container App."
  value       = azurerm_container_app.api.ingress[0].fqdn
}

output "ui_url" {
  description = "Public HTTPS FQDN of the web UI Container App."
  value       = azurerm_container_app.ui.ingress[0].fqdn
}

output "airflow_webserver_url" {
  description = "Public HTTPS FQDN of the Airflow webserver Container App."
  value       = azurerm_container_app.airflow_webserver.ingress[0].fqdn
}

output "log_analytics_workspace_id" {
  description = "Resource ID of the Log Analytics Workspace backing both Container Apps logs and the Postgres diagnostic setting."
  value       = azurerm_log_analytics_workspace.this.id
}
