# GrimWaves API - Terraform Compute Module

This module manages the DigitalOcean infrastructure for the GrimWaves API deployment.

## Resources Created

- DigitalOcean Droplet for the application
- DigitalOcean Volume for persistent data storage
- DigitalOcean Project for resource organization
- DigitalOcean VPC for network isolation
- DigitalOcean Firewall for security
- DigitalOcean Domain records for DNS
- DigitalOcean Load Balancer (production only)
- DigitalOcean Spaces bucket (production only)

## Usage

```hcl
module "grimwaves_staging" {
  source = "./.cicd/terraform/compute"
  
  do_token            = var.do_token
  ssh_key_fingerprint = var.ssh_key_fingerprint
  environment         = "staging"
  domain_name         = "grimwaves.com"
}
```

## Variables

| Name | Description | Type | Default |
|------|-------------|------|---------|
| do_token | DigitalOcean API Token | string | - |
| ssh_key_fingerprint | SSH key fingerprint for DigitalOcean droplets | string | - |
| project_name | Project name, used for resource naming | string | "grimwaves" |
| environment | Environment (staging or production) | string | "staging" |
| region | DigitalOcean region | string | "fra1" |
| droplet_size | Size of the droplet | map | `{staging = "s-1vcpu-1gb", production = "s-2vcpu-2gb"}` |
| volume_size | Size of the data volume in GB | map | `{staging = 10, production = 25}` |
| domain_name | Main domain name | string | "grimwaves.com" |
| enable_monitoring | Enable DigitalOcean monitoring | bool | true |
| enable_backups | Enable automated backups | map | `{staging = false, production = true}` |
| blue_green_deployment | Whether to use blue-green deployment | map | `{staging = false, production = true}` |

## Outputs

| Name | Description |
|------|-------------|
| droplet_id | ID of the created droplet |
| droplet_ipv4 | Public IPv4 address of the droplet |
| droplet_name | Name of the droplet |
| volume_id | ID of the data volume |
| project_id | ID of the DigitalOcean project |
| app_url | URL to access the application |
| active_color | The active color for blue-green deployment (if enabled) |
| inactive_color | The inactive color for blue-green deployment (if enabled) |
| deployment_info | Information about the deployment |

## Blue-Green Deployment

For production environments, the module supports Blue-Green deployment:

1. Two separate environments are created (blue and green)
2. The load balancer points to the active environment
3. For updates, deploy to the inactive environment
4. Test the inactive environment
5. Switch the load balancer to point to the newly updated environment

## Required Secrets in Vault

The following secrets should be stored in Vault:

- DigitalOcean API Token: `kv/digitalocean/api_token`
- SSH Key Fingerprint: `kv/digitalocean/ssh_key_fingerprint`
- SSH Private Key: `kv/ssh/private_key` 