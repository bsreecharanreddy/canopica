variable "project_name" {
  description = "Short, DNS-safe name prefixed onto every resource -- matches this repo's own \"canopica\" naming (e.g. CANOPICA_OPERATIONAL_DSN)."
  type        = string
  default     = "canopica"
}

variable "environment" {
  description = "Deployment tier suffix (e.g. demo, dev). Never \"prod\" -- this configuration is reference-only, never applied (see README.md)."
  type        = string
  default     = "demo"
}

variable "location" {
  description = "Azure region. A commercial-Azure region name by default; pair with the usgovcloud provider swap (providers.tf) and a usgovcloud region (e.g. usgovvirginia) to retarget."
  type        = string
  default     = "eastus"
}

variable "postgres_location" {
  description = "Region for the Postgres Flexible Server specifically, separate from var.location. Found live during Phase 5 Task 2's real apply: a fresh Azure Free Trial subscription can have zero Postgres Flexible Server SKU capacity in an otherwise-normal region (confirmed via `az postgres flexible-server list-skus --location eastus` returning an empty list, a 400 ParameterOutOfRange at apply time, not a config mistake) while neighboring regions (centralus, westus3, northeurope, checked live) have it -- a subscription-level capacity quirk, not something a real production subscription would hit. Defaults to var.location so this config's normal behavior is unchanged; override only if the same gap resurfaces."
  type        = string
  default     = null
}

variable "postgres_admin_login" {
  description = "Administrator login for the Postgres Flexible Server. The password is generated (random_password.postgres_admin in main.tf), never a literal here."
  type        = string
  default     = "canopicaadmin"
}

variable "api_image" {
  description = "Fully-qualified image ref for the API, e.g. <container-registry-login-server>/api:<tag>, pushed to the registry this configuration provisions."
  type        = string
}

variable "ui_image" {
  description = "Fully-qualified image ref for the web frontend."
  type        = string
}

variable "airflow_image" {
  description = "Fully-qualified image ref shared by the Airflow webserver and scheduler container apps, built from infra/airflow/Dockerfile."
  type        = string
}

variable "tags" {
  description = "Common resource tags applied across every resource in this configuration."
  type        = map(string)
  default = {
    project    = "canopica"
    managed_by = "terraform"
  }
}
