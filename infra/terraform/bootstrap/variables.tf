variable "project_id" {
  description = "GCP project id. Set in the git-ignored prod.tfvars, never in code."
  type        = string
}

variable "region" {
  description = "Region for the state bucket; us-central1 is inside the Cloud Storage free tier."
  type        = string
  default     = "us-central1"
}

variable "state_versions_kept" {
  description = "Non-current versions of each state object to keep."
  type        = number
  default     = 10
}
