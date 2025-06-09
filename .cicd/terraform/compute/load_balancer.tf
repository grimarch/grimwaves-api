# For production, create a load balancer if using blue-green deployment
resource "digitalocean_loadbalancer" "public" {
  count   = var.environment == "production" && lookup(var.blue_green_deployment, var.environment, false) ? 1 : 0
  name    = "${local.name_prefix}-lb"
  region  = var.region
  vpc_uuid = digitalocean_vpc.grimwaves_vpc.id

  forwarding_rule {
    entry_port     = 443
    entry_protocol = "https"
    target_port     = 443
    target_protocol = "https"
    tls_passthrough = true
  }

  forwarding_rule {
    entry_port     = 80
    entry_protocol = "http"
    target_port     = 80
    target_protocol = "http"
  }

  healthcheck {
    port     = 80
    protocol = "http"
    path     = "/health"
  }

  droplet_ids = [digitalocean_droplet.app.id]
}
