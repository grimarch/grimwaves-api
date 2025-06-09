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
