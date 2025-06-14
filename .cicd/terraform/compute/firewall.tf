
# Configure firewall to restrict access
resource "digitalocean_firewall" "web" {
  name = "${local.name_prefix}-firewall"

  # Allow HTTP and HTTPS from anywhere for web access
  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"] # Open to internet for web access
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"] # Open to internet for web access
  }

  # Inbound rules for DEBUG purposes
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = [var.vpn_ip]
  }


  # Inbound rules
  inbound_rule {
    protocol         = "tcp"
    port_range       = var.ssh_port                # SSH on non-standard port
    source_addresses = concat(var.allowed_ssh_cidr_blocks, [var.vpn_ip]) # Only from allowed IPs
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

  outbound_rule {
    protocol              = "tcp"
    port_range            = "8200-8250"
    destination_addresses = ["${var.vault_server_ip}/32"]
  }

  droplet_ids = [digitalocean_droplet.app.id]
}
