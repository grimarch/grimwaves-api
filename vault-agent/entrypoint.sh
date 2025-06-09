#!/bin/sh
set -e

# Set default values if variables are not specified
VAULT_ADDR=${VAULT_ADDR:-"https://vault-docker-lab1.vault-docker-lab.lan:8200"}
VAULT_SKIP_VERIFY=${VAULT_SKIP_VERIFY:-false}
VAULT_ROLE_NAME=${VAULT_ROLE_NAME:-"vault-agent"}

# Create directory for config if it doesn't exist
mkdir -p /vault-agent/config

# Replace variables in template and create configuration file
sed -e "s|\${VAULT_ADDR}|${VAULT_ADDR}|g" \
    -e "s|\${VAULT_SKIP_VERIFY}|${VAULT_SKIP_VERIFY}|g" \
    -e "s|\${VAULT_ROLE_NAME}|${VAULT_ROLE_NAME}|g" \
    /vault-agent/templates/agent.hcl.tpl > /vault-agent/config/agent.hcl

echo "Vault Agent configuration created with environment variable substitution"

# Start Vault Agent with the created configuration
exec vault agent -config=/vault-agent/config/agent.hcl