terraform {
  backend "s3" {
    # DigitalOcean Spaces S3-compatible backend
    endpoint                    = "https://fra1.digitaloceanspaces.com"
    region                      = "fra1"
    bucket                      = "grimwaves-terraform-state"
    key                         = "compute/terraform.tfstate"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    force_path_style            = true
    use_lockfile                = true
  }
}