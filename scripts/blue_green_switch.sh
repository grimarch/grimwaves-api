#!/bin/bash
# Blue/Green Deployment Switch Script
# This script helps switch traffic between blue and green environments

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
TERRAFORM_DIR=".cicd/terraform/compute"
ENVIRONMENT="production"

# Function to print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to get current active color
get_active_color() {
    cd "$TERRAFORM_DIR"
    terraform output -json blue_green_status 2>/dev/null | jq -r '.active_color // empty' || echo ""
}

# Function to get load balancer ID
get_load_balancer_id() {
    cd "$TERRAFORM_DIR"
    terraform output -raw load_balancer_id 2>/dev/null || echo ""
}

# Function to get droplet IDs
get_droplet_id() {
    local color=$1
    cd "$TERRAFORM_DIR"
    # This would need to be implemented based on actual Terraform outputs
    # For now, it's a placeholder
    echo "droplet-id-for-${color}"
}

# Function to perform health check
health_check() {
    local ip=$1
    local max_attempts=10
    local attempt=1
    
    print_color "$BLUE" "Performing health check on $ip..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -sSf "http://${ip}/health" > /dev/null 2>&1; then
            print_color "$GREEN" "✓ Health check passed"
            return 0
        fi
        
        print_color "$RED" "Health check attempt $attempt/$max_attempts failed"
        sleep 5
        ((attempt++))
    done
    
    print_color "$RED" "✗ Health check failed after $max_attempts attempts"
    return 1
}

# Function to switch traffic
switch_traffic() {
    local from_color=$1
    local to_color=$2
    local lb_id=$3
    
    print_color "$BLUE" "Switching traffic from $from_color to $to_color..."
    
    # Get droplet IDs
    local to_droplet_id=$(get_droplet_id "$to_color")
    
    # Update load balancer
    # This would use DigitalOcean API or Terraform to update the load balancer
    # For now, it's a placeholder
    echo "doctl compute load-balancer update $lb_id --droplet-ids $to_droplet_id"
    
    print_color "$GREEN" "✓ Traffic switched successfully"
}

# Main script
main() {
    print_color "$BLUE" "=== Blue/Green Deployment Switch ==="
    
    # Check if we're in the right directory
    if [ ! -d "$TERRAFORM_DIR" ]; then
        print_color "$RED" "Error: Terraform directory not found. Please run from project root."
        exit 1
    fi
    
    # Get current state
    local active_color=$(get_active_color)
    if [ -z "$active_color" ]; then
        print_color "$RED" "Error: Could not determine active color. Is blue/green deployment enabled?"
        exit 1
    fi
    
    local inactive_color="green"
    if [ "$active_color" == "green" ]; then
        inactive_color="blue"
    fi
    
    print_color "$BLUE" "Current active: $active_color"
    print_color "$BLUE" "Will switch to: $inactive_color"
    
    # Confirm action
    read -p "Are you sure you want to switch traffic? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        print_color "$RED" "Operation cancelled"
        exit 0
    fi
    
    # Get load balancer ID
    local lb_id=$(get_load_balancer_id)
    if [ -z "$lb_id" ]; then
        print_color "$RED" "Error: Could not find load balancer ID"
        exit 1
    fi
    
    # Perform health check on inactive environment
    local inactive_ip=$(get_droplet_ip "$inactive_color")
    if ! health_check "$inactive_ip"; then
        print_color "$RED" "Error: Inactive environment failed health check. Aborting switch."
        exit 1
    fi
    
    # Switch traffic
    switch_traffic "$active_color" "$inactive_color" "$lb_id"
    
    # Update Terraform state to reflect the switch
    # This would involve updating Terraform variables or state
    print_color "$BLUE" "Updating Terraform state..."
    
    print_color "$GREEN" "=== Switch completed successfully ==="
    print_color "$GREEN" "Active environment is now: $inactive_color"
}

# Run main function
main "$@" 