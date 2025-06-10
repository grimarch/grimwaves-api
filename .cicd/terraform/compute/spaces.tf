# Create a Space (S3-compatible storage) for backups and artifacts
resource "digitalocean_spaces_bucket" "storage" {
  count  = var.environment == "production" ? 1 : 0
  name   = "${var.project_name}-prod-storage-2025"
  region = var.region
  acl    = "private"
}
