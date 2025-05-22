resource "vault_approle_auth_backend_role" "vault_agent" { # Renamed from grimwaves
  backend        = vault_auth_backend.approle.path
  role_name      = "${var.project_name}-vault-agent"
  token_policies = [vault_policy.vault_agent.name]
  token_ttl      = 3600    # 1 hour (as in script)
  token_max_ttl  = 86400   # 24 hours (as in script)
  secret_id_ttl  = 604800  # 7 days (reduced from 30 days)
  # Add CIDR restrictions based on the network Vault server resides in
  secret_id_bound_cidrs = []
  token_bound_cidrs     = []
  # secret_id_num_uses = 0 # Default is 0 (infinite)
}

# Resource to generate one Secret ID for the role
resource "vault_approle_auth_backend_role_secret_id" "agent_secret_id" { # Renamed from id
  backend   = vault_auth_backend.approle.path
  role_name = vault_approle_auth_backend_role.vault_agent.role_name
}

# Commenting out wrapped token generation as it was conditional in script
# resource "vault_approle_auth_backend_role_secret_id" "grimwaves_wrapped" {
#   backend       = vault_auth_backend.approle.path
#   role_name     = vault_approle_auth_backend_role.vault_agent.role_name
#   wrapping_ttl  = "15m" # As in script
# }
