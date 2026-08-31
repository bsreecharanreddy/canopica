# Resources modeled here map onto this repo's own components (see
# README.md's table): Postgres stands in for infra/docker-compose.yml's
# `postgres` service (three databases, same names, on one server, same as
# the compose stack's own `postgres/init` scripts); Container Apps stand
# in for `api`, `ui`, `airflow-webserver`, and
# `airflow-scheduler`; Key Vault is the Secrets row's real-production
# target and Log Analytics/Azure Monitor is the Observability row's
# (tradeoffs doc). Keycloak, Metabase, and the Jaeger/Prometheus/Grafana
# stack are deliberately not modeled -- out of this task's own resource
# list (see the implementation plan's Task 10 section and README.md's
# "what's deliberately absent").

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  acr_name    = replace("${local.name_prefix}acr", "-", "")
}

resource "azurerm_resource_group" "this" {
  name     = "${local.name_prefix}-rg"
  location = var.location
  tags     = var.tags
}

# --- Secrets -----------------------------------------------------------

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "this" {
  name                       = "${local.name_prefix}-kv"
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = false
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = ["Get", "List", "Set"]
  }

  tags = var.tags
}

resource "random_password" "postgres_admin" {
  length  = 24
  special = true
}

resource "azurerm_key_vault_secret" "postgres_admin_password" {
  name         = "postgres-admin-password"
  value        = random_password.postgres_admin.result
  key_vault_id = azurerm_key_vault.this.id
}

# --- Data layer: Postgres Flexible Server stands in for the operational +
# serving Postgres in infra/docker-compose.yml -----------------------------

resource "azurerm_postgresql_flexible_server" "this" {
  name                = "${local.name_prefix}-psql"
  resource_group_name = azurerm_resource_group.this.name
  location            = coalesce(var.postgres_location, azurerm_resource_group.this.location)
  version             = "16"

  # Public access, no delegated subnet/private DNS zone -- a real
  # deployment would put this behind VNet integration and private
  # endpoints (the azurerm_postgresql_flexible_server example does this);
  # left out here so this reference config's resource list matches the
  # plan's own stated scope instead of growing into a full network design.
  public_network_access_enabled = true

  administrator_login    = var.postgres_admin_login
  administrator_password = random_password.postgres_admin.result

  storage_mb   = 32768
  storage_tier = "P4"
  sku_name     = "B_Standard_B1ms"

  tags = var.tags

  # Azure auto-assigns an availability zone at create time; this config
  # never sets one, but the provider still surfaces it as drift on every
  # later plan and rejects the resulting "change" outright (found live,
  # Phase 5 Task 2's real apply: "`zone` can only be changed when
  # exchanged with... `standby_availability_zone`") since a zone-only
  # change isn't actually a valid operation without also touching HA.
  lifecycle {
    ignore_changes = [zone]
  }
}

# `public_network_access_enabled` above only turns the *feature* on --
# found live, Phase 5 Task 2's real apply: with zero firewall rules, the
# Container Apps below could not reach Postgres at all (HikariCP hung on
# every connection attempt, Spring Boot's startup timed out, the JVM
# exited, Container Apps reported the revision as crash-looping). This
# rule is Azure's documented convention for "allow any Azure service" --
# the same shape a real deployment would tighten into VNet integration +
# private endpoints (already-documented absent, see README.md), not a
# new gap this fix introduces.
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Found live, same apply: `V6__audit_event.sql`'s real Flyway migration
# runs `create extension if not exists pgcrypto` (the audit chain's
# hashing) -- Azure Postgres Flexible Server rejects any extension not
# explicitly allow-listed on the server first, even for the admin login,
# a platform-specific gate self-hosted Postgres has no equivalent of.
resource "azurerm_postgresql_flexible_server_configuration" "allowed_extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "pgcrypto"
}

# One server, three databases -- same shape as postgres/init's real
# CREATE DATABASE statements (canopica_operational, canopica_serving, airflow).
resource "azurerm_postgresql_flexible_server_database" "operational" {
  name      = "canopica_operational"
  server_id = azurerm_postgresql_flexible_server.this.id
}

resource "azurerm_postgresql_flexible_server_database" "serving" {
  name      = "canopica_serving"
  server_id = azurerm_postgresql_flexible_server.this.id
}

resource "azurerm_postgresql_flexible_server_database" "airflow" {
  name      = "airflow"
  server_id = azurerm_postgresql_flexible_server.this.id
}

# --- Observability: Azure Monitor / Log Analytics is the Observability
# row's real-production target (tradeoffs doc) -- both the Container App
# Environment's own logs and the Postgres server's logs land here. ------

resource "azurerm_log_analytics_workspace" "this" {
  name                = "${local.name_prefix}-logs"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

resource "azurerm_monitor_diagnostic_setting" "postgres" {
  name                       = "${local.name_prefix}-psql-diagnostics"
  target_resource_id         = azurerm_postgresql_flexible_server.this.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id

  enabled_log {
    category_group = "allLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}

# --- Container images ----------------------------------------------------

resource "azurerm_container_registry" "this" {
  name                = local.acr_name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "Basic"

  # Admin credentials (below), not identity-based ACR pull -- simpler to
  # reference for a config that's read, not applied; a real deployment
  # would grant each Container App's managed identity AcrPull instead.
  admin_enabled = true

  tags = var.tags
}

# --- Compute: Container Apps stand in for api, ui, and
# both Airflow processes from infra/docker-compose.yml. -------------------

resource "azurerm_container_app_environment" "this" {
  name                       = "${local.name_prefix}-env"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = azurerm_resource_group.this.location
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  tags                       = var.tags
}

resource "azurerm_container_app" "api" {
  name                         = "${local.name_prefix}-api"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.this.login_server
    username             = azurerm_container_registry.this.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.this.admin_password
  }

  secret {
    name  = "postgres-password"
    value = random_password.postgres_admin.result
  }

  ingress {
    external_enabled = true
    target_port      = 8080
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    container {
      name   = "api"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "CANOPICA_OPERATIONAL_JDBC_URL"
        value = "jdbc:postgresql://${azurerm_postgresql_flexible_server.this.fqdn}:5432/canopica_operational"
      }
      env {
        name  = "CANOPICA_OPERATIONAL_USER"
        value = var.postgres_admin_login
      }
      env {
        name        = "CANOPICA_OPERATIONAL_PASSWORD"
        secret_name = "postgres-password"
      }
      # Not set here, deliberately: CANOPICA_KEYCLOAK_*_JWKS_URI (no Keycloak
      # modeled in this reference) and CANOPICA_OTLP_TRACES_ENDPOINT (no
      # Jaeger/Azure Monitor OTLP ingestion modeled -- see README.md).
    }
  }

  tags = var.tags
}

resource "azurerm_container_app" "ui" {
  name                         = "${local.name_prefix}-ui"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.this.login_server
    username             = azurerm_container_registry.this.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.this.admin_password
  }

  ingress {
    external_enabled = true
    target_port      = 80
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    container {
      name   = "ui"
      image  = var.ui_image
      cpu    = 0.25
      memory = "0.5Gi"

      # Found live, Phase 5 Task 2's real apply: nginx.conf.template's
      # default (Docker Compose's "api:8080") doesn't resolve here --
      # Container Apps addresses a sibling app by its own resource name
      # (no port; ingress already knows the target port). Without this,
      # nginx fails its own config parse at startup and the container
      # never comes up at all (`host not found in upstream "api"`).
      env {
        name  = "API_UPSTREAM"
        value = azurerm_container_app.api.name
      }
    }
  }

  tags = var.tags
}

resource "azurerm_container_app" "airflow_webserver" {
  name                         = "${local.name_prefix}-airflow-web"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.this.login_server
    username             = azurerm_container_registry.this.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.this.admin_password
  }

  secret {
    name  = "airflow-sql-alchemy-conn"
    value = "postgresql+psycopg2://${var.postgres_admin_login}:${random_password.postgres_admin.result}@${azurerm_postgresql_flexible_server.this.fqdn}:5432/airflow"
  }

  ingress {
    external_enabled = true
    target_port      = 8080
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    container {
      name   = "airflow-webserver"
      image  = var.airflow_image
      cpu    = 0.5
      memory = "1Gi"
      # Compose's own `command: webserver` overrides the base Airflow
      # image's CMD only, keeping its ENTRYPOINT script -- `args`, not
      # `command`, is the Container App equivalent of that.
      args = ["webserver"]

      env {
        name  = "AIRFLOW__CORE__EXECUTOR"
        value = "LocalExecutor"
      }
      env {
        name        = "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"
        secret_name = "airflow-sql-alchemy-conn"
      }
      env {
        name  = "AIRFLOW__CORE__LOAD_EXAMPLES"
        value = "false"
      }
      env {
        name  = "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION"
        value = "false"
      }
    }
  }

  tags = var.tags
}

resource "azurerm_container_app" "airflow_scheduler" {
  name                         = "${local.name_prefix}-airflow-sched"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.this.login_server
    username             = azurerm_container_registry.this.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.this.admin_password
  }

  secret {
    name  = "airflow-sql-alchemy-conn"
    value = "postgresql+psycopg2://${var.postgres_admin_login}:${random_password.postgres_admin.result}@${azurerm_postgresql_flexible_server.this.fqdn}:5432/airflow"
  }

  # No ingress -- LocalExecutor runs every task as a subprocess of the
  # scheduler itself, same as infra/docker-compose.yml's own
  # airflow-scheduler service, which likewise exposes no port.
  template {
    container {
      name   = "airflow-scheduler"
      image  = var.airflow_image
      cpu    = 0.5
      memory = "1Gi"
      args   = ["scheduler"]

      env {
        name  = "AIRFLOW__CORE__EXECUTOR"
        value = "LocalExecutor"
      }
      env {
        name        = "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"
        secret_name = "airflow-sql-alchemy-conn"
      }
      env {
        name  = "AIRFLOW__CORE__LOAD_EXAMPLES"
        value = "false"
      }
      env {
        name  = "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION"
        value = "false"
      }
    }
  }

  tags = var.tags
}
