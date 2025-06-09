# Create Droplet for the application
resource "digitalocean_droplet" "app" {
  image              = var.droplet_image
  name               = local.droplet_name
  region             = var.region
  size               = lookup(var.droplet_size, var.environment)
  vpc_uuid           = digitalocean_vpc.grimwaves_vpc.id
  ssh_keys           = [var.ssh_key_fingerprint]
  monitoring         = var.enable_monitoring
  backups            = lookup(var.enable_backups, var.environment, false)
  tags               = local.tags
  
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