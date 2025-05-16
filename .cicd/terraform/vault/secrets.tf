# resource "vault_mount" "kv2" {
#   path = "secret" # Use 'secret' path as in setup-vault.sh
#   type = "kv"
#   options = {
#     version = "2"
#   }
#   description = "KV Version 2 secret engine for ${var.project_name}"
# }

resource "vault_kv_secret_v2" "spotify" {
  mount = "secret" # Use the existing default 'secret' mount path
  name  = "${var.project_name}/dev/streaming/spotify"

  data_json = jsonencode({
    client_id     = var.spotify_client_id
    client_secret = var.spotify_client_secret
  })
}

resource "vault_kv_secret_v2" "config" {
  mount = "secret" # Use the existing default 'secret' mount path
  name  = "${var.project_name}/dev/config"

  data_json = jsonencode({
    CELERY_BROKER_URL     = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND = "redis://redis:6379/0"
    REDIS_URL             = "redis://redis:6379/1"
  })
}
