output "role_id" {
  description = "The RoleID of the AppRole"
  value       = vault_approle_auth_backend_role.vault_agent.role_id
}

output "secret_id" {
  description = "A SecretID for the AppRole"
  value       = vault_approle_auth_backend_role_secret_id.agent_secret_id.secret_id
  sensitive   = true
}

# Commenting out wrapped token output as generation is commented out
# output "wrapped_secret_id_token" {
#   description = "A wrapped token containing a SecretID for the AppRole"
#   value     = vault_approle_auth_backend_role_secret_id.grimwaves_wrapped.wrapping_token
#   sensitive = true
# }

# Add local_file resources to save credentials for Vault Agent
resource "local_file" "role_id_file" {
  content  = vault_approle_auth_backend_role.vault_agent.role_id
  filename = "../../../vault-agent/auth/role-id" # Relative path from .cicd/terraform/vault to vault-agent/auth
  file_permission = "0600"

  depends_on = [vault_approle_auth_backend_role.vault_agent]
}

resource "local_sensitive_file" "secret_id_file" {
  content  = vault_approle_auth_backend_role_secret_id.agent_secret_id.secret_id
  filename = "../../../vault-agent/auth/secret-id" # Relative path
  file_permission = "0600"

  depends_on = [vault_approle_auth_backend_role_secret_id.agent_secret_id]
}
