auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path = "/vault-agent/auth/role-id"
      secret_id_file_path = "/vault-agent/auth/secret-id"
      remove_secret_id_file_after_reading = false
      role_name = "${VAULT_ROLE_NAME}"
    }
  }

  sink "file" {
    perms = 0600 # Ensure only the agent process owner can read/write the token
    config = {
      path = "/vault-agent/token/vault-token"
    }
  }
}

vault {
  address = "https://vault-docker-lab1.vault-docker-lab.lan:8200"
  tls_skip_verify = false
  ca_cert = "/vault-agent/certs/vault_docker_lab_ca.pem"
}

listener "unix" {
  address = "/vault-agent/sockets/agent.sock"
  socket_mode = "0600"  # Только владелец может читать и писать
  tls_disable = true
}

# Шаблон для секретов
template {
  source = "/vault-agent/templates/env.tpl"
  destination = "/vault-agent/rendered/.env"
  error_on_missing_key = true
  perms = 0400  # Только владелец может читать, никто не может писать
}
