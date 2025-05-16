provider "vault" {
  address = "https://127.0.0.1:8200"
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
