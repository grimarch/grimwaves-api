terraform {
  backend "s3" {
    # DigitalOcean Spaces S3-compatible backend
    endpoints = {
      s3 = "https://fra1.digitaloceanspaces.com"
    }
    region                      = "fra1"
    bucket                      = "grimwaves-terraform-state"
    # key will be passed dynamically through -backend-config

    # Disable AWS-specific validations for DigitalOcean Spaces
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    
    use_path_style              = true
  }
}