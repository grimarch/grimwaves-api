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
  user_data = templatefile("${path.module}/templates/cloud-init.sh", {
    network_utils_content = file("${path.module}/templates/utils/network.sh")
    docker_utils_content  = file("${path.module}/templates/utils/docker.sh")
    agent_utils_content   = file("${path.module}/templates/utils/agent.sh")
    ssh_port              = var.ssh_port
    project_name          = var.project_name
    environment           = var.environment
    ssh_public_key        = var.ssh_public_key
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

  # Allow HTTP and HTTPS from anywhere (restricted to known networks in production)
  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = var.allowed_ssh_cidr_blocks # Only from allowed IPs
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = var.allowed_ssh_cidr_blocks # Only from allowed IPs
  }

  # Inbound rules
  inbound_rule {
    protocol         = "tcp"
    port_range       = var.ssh_port                # SSH on non-standard port
    source_addresses = var.allowed_ssh_cidr_blocks # Only from allowed IPs
  }

  # Enable emergency global SSH access if flag is true
  dynamic "inbound_rule" {
    for_each = var.emergency_ssh_access ? [1] : []
    content {
      protocol         = "tcp"
      port_range       = var.ssh_port
      source_addresses = ["0.0.0.0/0"]
    }
  }

  # HTTP (80) - SECURITY COMPROMISE: Open to internet due to dynamic CDN IPs
  # ⚠️ RISK: Docker Hub, Ubuntu repos use AWS ELB with changing IPs
  # ⚠️ Static IP restrictions would break package installations
  outbound_rule {
    protocol              = "tcp"
    port_range            = "80"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  # HTTPS (443) - SECURITY COMPROMISE: Open to internet due to dynamic CDN IPs  
  # ⚠️ RISK: Same as HTTP - modern services use dynamic IPs via CDN
  # ⚠️ Alternative: Use corporate proxy/registry (Nexus, Artifactory)
  outbound_rule {
    protocol              = "tcp"
    port_range            = "443"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  # DNS resolution - Allow DigitalOcean DNS servers + trusted public DNS servers  
  outbound_rule {
    protocol   = "udp"
    port_range = "53"
    destination_addresses = [
      "67.207.67.2/32",  # DigitalOcean DNS Primary
      "67.207.67.3/32",  # DigitalOcean DNS Secondary
      "67.207.67.4/32",  # DigitalOcean DNS Tertiary
      "8.8.8.8/32",      # Google DNS Primary
      "8.8.4.4/32",      # Google DNS Secondary  
      "1.1.1.1/32",      # Cloudflare DNS Primary
      "1.0.0.1/32"       # Cloudflare DNS Secondary
    ]
  }

  outbound_rule {
    protocol   = "tcp"
    port_range = "53"
    destination_addresses = [
      "67.207.67.2/32",  # DigitalOcean DNS Primary
      "67.207.67.3/32",  # DigitalOcean DNS Secondary
      "67.207.67.4/32",  # DigitalOcean DNS Tertiary
      "8.8.8.8/32",      # Google DNS Primary
      "8.8.4.4/32",      # Google DNS Secondary
      "1.1.1.1/32",      # Cloudflare DNS Primary  
      "1.0.0.1/32"       # Cloudflare DNS Secondary
    ]
  }

  # NTP (123) - STRICTLY LIMITED to verified government time servers
  outbound_rule {
    protocol   = "udp"
    port_range = "123"
    destination_addresses = [
      "129.6.15.28/32",  # time-a-g.nist.gov
      "129.6.15.29/32",  # time-b-g.nist.gov  
      "129.6.15.30/32",  # time-c-g.nist.gov
      "132.163.97.1/32", # time-a-wwv.nist.gov
      "132.163.97.2/32"  # time-b-wwv.nist.gov
    ]
  }

  # Allow monitoring and essential ICMP
  outbound_rule {
    protocol              = "icmp"
    destination_addresses = [
      "8.8.8.8",             # Google DNS (for ping-test)
      "1.1.1.1",             # Cloudflare DNS
      "169.254.169.254",     # Cloud metadata
      "10.0.0.0/16"          # Internal subnets (for ping-test)
    ]
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