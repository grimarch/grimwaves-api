provider "digitalocean" {
  token = var.do_token
}

resource "digitalocean_droplet" "web" {
  image  = "ubuntu-22-04-x64"
  name   = "grimwaves-dev"
  region = "fra1"
  size   = "s-1vcpu-1gb"
  ssh_keys = [var.ssh_key_fingerprint]
}