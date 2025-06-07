output "droplet_id" {
  description = "ID of the created droplet"
  value       = digitalocean_droplet.app.id
}

output "droplet_ipv4" {
  description = "IPv4 address of the droplet"
  value       = digitalocean_droplet.app.ipv4_address
}

output "droplet_name" {
  description = "Name of the droplet"
  value       = digitalocean_droplet.app.name
}

output "volume_id" {
  description = "ID of the data volume"
  value       = digitalocean_volume.data.id
}

output "project_id" {
  description = "ID of the DigitalOcean project"
  value       = digitalocean_project.grimwaves.id
}

output "app_url" {
  description = "Application URL"
  # If domain_name is overridden via TF_VAR_domain_name, use it directly
  # Otherwise use predefined app_domains mapping
  value = var.domain_name != "grimwaves.duckdns.org" ? "https://${var.domain_name}" : "https://${lookup(var.app_domains, var.environment)}"
}

output "active_color" {
  description = "The active color for blue-green deployment (if enabled)"
  value       = local.active_color
}

output "inactive_color" {
  description = "The inactive color for blue-green deployment (if enabled)"
  value       = local.inactive_color
}

output "deployment_info" {
  description = "Information about the deployment"
  value = {
    environment      = var.environment
    region           = var.region
    blue_green       = lookup(var.blue_green_deployment, var.environment, false)
    monitoring       = var.enable_monitoring
    backups_enabled  = lookup(var.enable_backups, var.environment, false)
    domain           = var.domain_name != "grimwaves.duckdns.org" ? var.domain_name : lookup(var.app_domains, var.environment)
  }
}

output "load_balancer_id" {
  value = var.environment == "production" && lookup(var.blue_green_deployment, var.environment, false) ? digitalocean_loadbalancer.public[0].id : null
  description = "Load balancer ID for blue/green deployment"
}

output "load_balancer_ip" {
  value = var.environment == "production" && lookup(var.blue_green_deployment, var.environment, false) ? digitalocean_loadbalancer.public[0].ip : null
  description = "Load balancer IP address"
}

output "active_droplet_ip" {
  value = digitalocean_droplet.app.ipv4_address
  description = "IP address of the active droplet"
}

output "inactive_droplet_ip" {
  value = var.environment == "production" && lookup(var.blue_green_deployment, var.environment, false) ? digitalocean_droplet.app_inactive[0].ipv4_address : null
  description = "IP address of the inactive droplet (blue/green)"
}

output "ssh_port" {
  description = "SSH port used for connections to the droplet"
  value       = var.ssh_port
} 