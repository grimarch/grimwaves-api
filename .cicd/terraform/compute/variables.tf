variable "do_token" {
  description = "DigitalOcean API token"
  sensitive   = true
}

variable "ssh_key_fingerprint" {
  description = "SSH key fingerprint for DigitalOcean droplets"
}

variable "ssh_public_key" {
  description = "Public SSH key content for user authentication"
  type        = string
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
  default     = "grimwaves.duckdns.org"
}

variable "app_domains" {
  description = "Application domains for each environment"
  type        = map(string)
  default = {
    staging    = "staging-grimwaves.duckdns.org"
    production = "grimwaves.duckdns.org"
  }
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

variable "allowed_ssh_cidr_blocks" {
  description = "List of CIDR blocks that are allowed to access the instance via SSH. MUST be specified explicitly for security. WARNING: Using 0.0.0.0/0 opens SSH to the entire internet - use only for emergency access!"
  type        = list(string)
  # No default - user MUST provide explicit IP addresses for security

  validation {
    condition     = length(var.allowed_ssh_cidr_blocks) > 0
    error_message = "allowed_ssh_cidr_blocks must contain at least one CIDR block. Specify your IP address(es) or use emergency_ssh_access flag for temporary global access."
  }
}

variable "ssh_port" {
  description = "The port on which SSH service should listen."
  type        = number
  # default     = 2222 # Non-standard port for security
  default     = 22
}

variable "emergency_ssh_access" {
  description = "Enable emergency global SSH access to the Droplet."
  type        = bool
  default     = false
}