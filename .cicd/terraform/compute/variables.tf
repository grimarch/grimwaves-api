variable "do_token" {
  description = "DigitalOcean API token"
  sensitive   = true
}

variable "ssh_key_fingerprint" {
  description = "SSH key fingerprint for DigitalOcean droplets"
}

variable "project_name" {
  description = "Project name, used for resource naming"
  default     = "grimwaves"
}

variable "environment" {
  description = "Environment (staging or production)"
  default     = "staging"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be 'staging' or 'production'."
  }
}

variable "region" {
  description = "DigitalOcean region"
  default     = "fra1"
}

variable "droplet_size" {
  description = "Size of the droplet"
  default = {
    staging    = "s-1vcpu-1gb"
    production = "s-2vcpu-2gb"
  }
}

variable "volume_size" {
  description = "Size of the data volume in GB"
  default = {
    staging    = 10
    production = 25
  }
}

variable "domain_name" {
  description = "Main domain name"
  default     = "grimwaves.com"
}

variable "enable_monitoring" {
  description = "Enable DigitalOcean monitoring"
  default     = true
}

variable "enable_backups" {
  description = "Enable automated backups"
  default = {
    staging    = false
    production = true
  }
}

variable "blue_green_deployment" {
  description = "Whether to use blue-green deployment"
  default = {
    staging    = false
    production = true
  }
}