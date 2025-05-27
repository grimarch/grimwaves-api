output "droplet_id" {
  description = "ID of the created droplet"
  value       = digitalocean_droplet.app.id
}

output "droplet_ipv4" {
  description = "Public IPv4 address of the droplet"
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
  description = "URL to access the application"
  value = var.environment == "production" ? (
    length(digitalocean_loadbalancer.public) > 0 ? "https://api.${var.domain_name}" : "https://${digitalocean_droplet.app.ipv4_address}"
  ) : "https://api-staging.${var.domain_name}"
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
    domain           = var.domain_name
  }
} 