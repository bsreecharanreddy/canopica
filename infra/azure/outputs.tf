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
  description = "Login server for the Container Registry -- push portal_api_image/portal_web_image/airflow_image here before applying."
  value       = azurerm_container_registry.this.login_server
}

output "portal_api_url" {
  description = "Public HTTPS FQDN of the portal API Container App."
  value       = azurerm_container_app.portal_api.ingress[0].fqdn
}

output "portal_web_url" {
  description = "Public HTTPS FQDN of the portal web Container App."
  value       = azurerm_container_app.portal_web.ingress[0].fqdn
}

output "airflow_webserver_url" {
  description = "Public HTTPS FQDN of the Airflow webserver Container App."
  value       = azurerm_container_app.airflow_webserver.ingress[0].fqdn
}

output "log_analytics_workspace_id" {
  description = "Resource ID of the Log Analytics Workspace backing both Container Apps logs and the Postgres diagnostic setting."
  value       = azurerm_log_analytics_workspace.this.id
}
