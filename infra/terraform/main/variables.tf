# Environment values (project id, e-mail) come from the git-ignored prod.tfvars;
# prod.example.tfvars shows the shape.

variable "project_id" {
  description = "GCP project id."
  type        = string
}

variable "alert_email" {
  description = "Address that receives the security alerts (spec §14.9)."
  type        = string
  sensitive   = true
}

variable "owner_email" {
  description = "Google account of the owner; may impersonate sa-loader."
  type        = string
  sensitive   = true
}

variable "region" {
  description = "Region for buckets and the VM; us-central1 is inside the free tier for both."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zone for the collector VM."
  type        = string
  default     = "us-central1-a"
}

variable "bq_location" {
  description = "BigQuery location; the US multi-region can load from a bucket in any US region."
  type        = string
  default     = "US"
}

variable "github_repository_id" {
  description = "Numeric id of the GitHub repository allowed to use WIF. Unlike the name, it survives a rename and cannot be claimed by another repository."
  type        = string
  default     = "1410331255"
}

variable "dev_table_expiration_days" {
  description = "Lifetime of tables in the dev_* datasets (spec §14.8)."
  type        = number
  default     = 7
}

variable "create_vm" {
  description = "Create the collector VM, its network and the IAP firewall rule. On from S0.3b (2026-10-19): the local probe passed and a Linux licence slot is free; the VM probe is the cloud gate. The default lives here, not in tfvars, so local and CI plans agree."
  type        = bool
  default     = true
}

variable "vm_disk_size_gb" {
  description = "Boot disk size; the free tier covers 30 GB-months of standard persistent disk."
  type        = number
  default     = 30
}

variable "alert_rate_limit" {
  description = "Minimum time between two e-mails from the same log-based alert."
  type        = string
  default     = "300s"
}
