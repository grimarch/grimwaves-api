# Blue/Green Deployment Configuration
# This file contains resources specific to blue/green deployment strategy

# Data source to find existing droplets for blue/green
data "digitalocean_droplets" "existing" {
  filter {
    key    = "tags"
    values = local.tags
  }
}

# Create the inactive droplet for blue/green deployment
resource "digitalocean_droplet" "app_inactive" {
  count = var.environment == "production" && lookup(var.blue_green_deployment, var.environment, false) ? 1 : 0
  
  image              = "docker-20-04"
  name               = "${local.name_prefix}-${local.inactive_color}"
  region             = var.region
  size               = lookup(var.droplet_size, var.environment)
  vpc_uuid           = digitalocean_vpc.grimwaves_vpc.id
  ssh_keys           = [var.ssh_key_fingerprint]
  monitoring         = var.enable_monitoring
  backups            = lookup(var.enable_backups, var.environment, false)
  tags               = concat(local.tags, ["color:${local.inactive_color}", "status:inactive"])
  
  # Cloud-init script to set up Docker and docker-compose
  user_data = templatefile("${path.module}/templates/cloud-init.yml", {
    project_name = var.project_name
    environment  = var.environment
  })
}

# Attach volume to the inactive droplet
resource "digitalocean_volume" "data_inactive" {
  count                   = var.environment == "production" && lookup(var.blue_green_deployment, var.environment, false) ? 1 : 0
  name                    = "${local.name_prefix}-data-${local.inactive_color}"
  region                  = var.region
  size                    = lookup(var.volume_size, var.environment)
  initial_filesystem_type = "ext4"
  description             = "Data volume for ${local.name_prefix} ${local.inactive_color}"
  tags                    = concat(local.tags, ["color:${local.inactive_color}"])
}

resource "digitalocean_volume_attachment" "data_attachment_inactive" {
  count      = var.environment == "production" && lookup(var.blue_green_deployment, var.environment, false) ? 1 : 0
  droplet_id = digitalocean_droplet.app_inactive[0].id
  volume_id  = digitalocean_volume.data_inactive[0].id
}

# Update firewall to include inactive droplet
resource "digitalocean_firewall" "web_blue_green" {
  count = var.environment == "production" && lookup(var.blue_green_deployment, var.environment, false) ? 1 : 0
  name  = "${local.name_prefix}-firewall-blue-green"

  # Allow HTTP and HTTPS from load balancer only
  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_load_balancer_uids = [digitalocean_loadbalancer.public[0].id]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_load_balancer_uids = [digitalocean_loadbalancer.public[0].id]
  }

  # Allow SSH from restricted IPs
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.ssh_allowed_ips
  }

  # Allow all outbound traffic
  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
  
  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  droplet_ids = concat(
    [digitalocean_droplet.app.id],
    digitalocean_droplet.app_inactive[*].id
  )
}

# Output for blue/green status
output "blue_green_status" {
  value = var.environment == "production" && lookup(var.blue_green_deployment, var.environment, false) ? {
    active_color    = local.active_color
    inactive_color  = local.inactive_color
    active_droplet  = digitalocean_droplet.app.name
    inactive_droplet = try(digitalocean_droplet.app_inactive[0].name, "none")
    load_balancer   = try(digitalocean_loadbalancer.public[0].ip, "none")
  } : null
  description = "Blue/Green deployment status"
} 