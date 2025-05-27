provider "vault" {
  address = var.vault_address
  token   = var.vault_token
}

terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
  }
}
