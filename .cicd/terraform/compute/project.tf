# Create a DigitalOcean project
resource "digitalocean_project" "grimwaves" {
  name        = local.name_prefix
  description = "GrimWaves API ${var.environment} environment"
  purpose     = "Web Application"
  environment = var.environment
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