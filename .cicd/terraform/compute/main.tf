provider "digitalocean" {
  token = var.do_token
  
  # Configure Spaces credentials
  spaces_access_id  = var.spaces_access_key_id
  spaces_secret_key = var.spaces_secret_access_key
}

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
