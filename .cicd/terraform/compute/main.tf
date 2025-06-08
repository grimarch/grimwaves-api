terraform {
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.34"
    }
  }
  required_version = ">= 1.0"
}

provider "digitalocean" {
  token = var.do_token
}

# We'll use a variable for the public key instead of data source
# since we need the actual public key content for cloud-init

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  tags        = ["app:${var.project_name}", "env:${var.environment}", "managed-by:terraform"]
  
  # For blue-green deployment, determine active color
  active_color    = lookup(var.blue_green_deployment, var.environment, false) ? "blue" : null
  inactive_color  = lookup(var.blue_green_deployment, var.environment, false) ? "green" : null
  
  # Determine droplet name based on deployment strategy
  droplet_name = (
    lookup(var.blue_green_deployment, var.environment, false)
    ? "${local.name_prefix}-${local.active_color}"
    : local.name_prefix
  )
}

# Create a DigitalOcean project
resource "digitalocean_project" "grimwaves" {
  name        = local.name_prefix
  description = "GrimWaves API ${var.environment} environment"
  purpose     = "Web Application"
  environment = var.environment
}

# Create a DigitalOcean VPC for network isolation
resource "digitalocean_vpc" "grimwaves_vpc" {
  name     = "${local.name_prefix}-network"
  region   = var.region
  ip_range = var.environment == "production" ? "10.10.10.0/24" : "10.10.20.0/24"
}

# Create Droplet for the application
resource "digitalocean_droplet" "app" {
  image              = "docker-20-04"
  name               = local.droplet_name
  region             = var.region
  size               = lookup(var.droplet_size, var.environment)
  vpc_uuid           = digitalocean_vpc.grimwaves_vpc.id
  ssh_keys           = [var.ssh_key_fingerprint]
  monitoring         = var.enable_monitoring
  backups            = lookup(var.enable_backups, var.environment, false)
  tags               = local.tags
  
  # Cloud-init script to set up Docker and docker-compose
  user_data = templatefile("${path.module}/templates/cloud-init.yml", {
    project_name   = var.project_name
    environment    = var.environment
    ssh_public_key = var.ssh_public_key
    ssh_port       = var.ssh_port
  })
}

# Create a volume for persistent data
resource "digitalocean_volume" "data" {
  name                    = "${local.name_prefix}-data"
  region                  = var.region
  size                    = lookup(var.volume_size, var.environment)
  initial_filesystem_type = "ext4"
  description             = "Data volume for ${local.name_prefix}"
  tags                    = local.tags
}

# Attach volume to the droplet
resource "digitalocean_volume_attachment" "data_attachment" {
  droplet_id = digitalocean_droplet.app.id
  volume_id  = digitalocean_volume.data.id
}

# DNS records are managed externally via DuckDNS
# No DigitalOcean DNS resources needed

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

# Configure firewall to restrict access
resource "digitalocean_firewall" "web" {
  name = "${local.name_prefix}-firewall"

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

  droplet_ids = [digitalocean_droplet.app.id]
}

# Create a Space (S3-compatible storage) for backups and artifacts
resource "digitalocean_spaces_bucket" "storage" {
  count  = var.environment == "production" ? 1 : 0
  name   = "${var.project_name}-storage"
  region = var.region
  acl    = "private"
}

# Add resources to the project
resource "digitalocean_project_resources" "grimwaves" {
  project = digitalocean_project.grimwaves.id
  resources = concat(
    [digitalocean_droplet.app.urn],
    var.environment == "production" && lookup(var.blue_green_deployment, var.environment, false) ? [digitalocean_loadbalancer.public[0].urn] : [],
    var.environment == "production" ? [digitalocean_spaces_bucket.storage[0].urn] : []
  )
}