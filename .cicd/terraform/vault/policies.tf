resource "vault_policy" "vault_agent" { # Renamed from grimwaves to vault_agent
  name   = "${var.project_name}-vault-agent-policy"
  policy = <<-EOT
    # Grant read access to specific dev secrets for the project
    path "secret/data/${var.project_name}/dev/config" {
      capabilities = ["read"]
    }
    # Grant read access to all streaming service secrets
    path "secret/data/${var.project_name}/dev/streaming/*" {
      capabilities = ["read"]
    }
    # Allow the agent to renew its own token
    path "auth/token/renew-self" {
      capabilities = ["update"]
    }
    # Allow the agent to lookup its own token
    path "auth/token/lookup-self" {
      capabilities = ["read"]
    }
  EOT
}
