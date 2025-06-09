#!/bin/bash
# Script to get Vault server IP from Terraform and set environment variables
# Usage: source scripts/get-vault-ip.sh

set -e

TERRAFORM_DIR="../learn-vault-docker-lab"
ENV_FILE=".env"

echo "🔍 Getting Vault server IP from Terraform state..."

# Check if terraform directory exists
if [ ! -d "$TERRAFORM_DIR" ]; then
    echo "❌ Error: Terraform directory not found: $TERRAFORM_DIR"
    echo "💡 Please ensure learn-vault-docker-lab project is in the parent directory"
    exit 1
fi

# Change to terraform directory and get outputs
cd "$TERRAFORM_DIR"

# Check if terraform state exists
if [ ! -f "terraform.tfstate" ]; then
    echo "❌ Error: Terraform state not found. Please deploy Vault first:"
    echo "   cd $TERRAFORM_DIR && make deploy"
    exit 1
fi

# Extract IP addresses from terraform output
FLOATING_IP=$(terraform output -raw floating_ip_address 2>/dev/null || echo "")
DROPLET_IP=$(terraform output -raw droplet_public_ip 2>/dev/null || echo "")

# Use floating IP if available, otherwise use droplet IP
if [ -n "$FLOATING_IP" ] && [ "$FLOATING_IP" != "null" ]; then
    VAULT_IP="$FLOATING_IP"
    echo "✅ Using floating IP: $VAULT_IP"
elif [ -n "$DROPLET_IP" ] && [ "$DROPLET_IP" != "null" ]; then
    VAULT_IP="$DROPLET_IP"
    echo "✅ Using droplet IP: $VAULT_IP"
else
    echo "❌ Error: Could not get IP address from Terraform outputs"
    exit 1
fi

# Return to grimwaves-api directory
cd - > /dev/null

# Update or create .env file
echo "📝 Updating $ENV_FILE with Vault configuration..."

# Create .env file if it doesn't exist
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << EOF
# Auto-generated Vault configuration
# Generated on $(date)
VAULT_SERVER_IP=$VAULT_IP
VAULT_ADDR=https://vault-docker-lab1.vault-docker-lab.lan:8200
VAULT_PROJECT_NAME=learn-vault-lab

# Environment
ENVIRONMENT=development
EOF
    echo "✅ Created new $ENV_FILE file"
else
    # Update existing .env file
    if grep -q "VAULT_SERVER_IP=" "$ENV_FILE"; then
        sed -i "s/VAULT_SERVER_IP=.*/VAULT_SERVER_IP=$VAULT_IP/" "$ENV_FILE"
    else
        echo "VAULT_SERVER_IP=$VAULT_IP" >> "$ENV_FILE"
    fi
    echo "✅ Updated VAULT_SERVER_IP in $ENV_FILE"
fi

# Export for current session
export VAULT_SERVER_IP="$VAULT_IP"
export VAULT_ADDR="https://vault-docker-lab1.vault-docker-lab.lan:8200"
export VAULT_SKIP_VERIFY=true

echo "🚀 Environment configured! Current Vault IP: $VAULT_IP"
echo ""
echo "💡 To use this configuration:"
echo "   export VAULT_SERVER_IP=$VAULT_IP"
echo "   docker-compose up -d"
echo ""
echo "📋 Or source this script to export variables:"
echo "   source scripts/get-vault-ip.sh" 