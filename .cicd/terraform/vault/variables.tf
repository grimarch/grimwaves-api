variable "spotify_client_id" {
  description = "Spotify Client ID"
  type        = string
  sensitive   = true
}

variable "spotify_client_secret" {
  description = "Spotify Client Secret"
  type        = string
  sensitive   = true
}

variable "vault_address" {
  description = "Vault Address"
  type        = string
  default     = "https://127.0.0.1:8200"
}

variable "vault_token" {
  description = "Vault Token (admin privileges required for setup)"
  type        = string
  sensitive   = true # Token is sensitive
}

variable "project_name" {
  description = "Project name prefix for Vault resources"
  type        = string
  default     = "grimwaves-api"
}

variable "approle_path" {
  description = "Path for the AppRole auth backend"
  type        = string
  default     = "approle"
}
