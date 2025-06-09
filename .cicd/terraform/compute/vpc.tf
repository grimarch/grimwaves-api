# Create a DigitalOcean VPC for network isolation
resource "digitalocean_vpc" "grimwaves_vpc" {
  name     = "${local.name_prefix}-network"
  region   = var.region
  ip_range = var.environment == "production" ? "10.10.10.0/24" : "10.10.20.0/24"
}
