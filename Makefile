VAULT_TOKEN_FILE ?= ~/.vault-token
VAULT_ENV_SCRIPT := scripts/load_secrets_from_vault.py

.PHONY: dev prod down down-clean restart-dev restart-prod logs logs-api logs-traefik prune \
	help vault-init vault-apply vault-plan vault-edit vault-decrypt compose-logs logs-to-file logs-aggregated logs-watch flush-cache vault-check-env vault-test-connection vault-get-github-credentials

# ================= Docker Compose ====================

# Default target
all: help

dev: ## Run docker compose with dev environment
	@echo "⏳⚙️  Loading secrets from Vault and building development environment..."
	@VAULT_TOKEN=$$(cat ~/.vault-token) \
	poetry run python scripts/load_secrets_from_vault.py | tr '\n' ' ' | \
	xargs -I {} docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d {}

dev-build: ## Build and run docker compose with dev environment
	@echo "⏳⚙️   Loading secrets from Vault and building development environment..."
	@export VAULT_TOKEN=$$(cat ~/.vault-token); \
	poetry run python scripts/load_secrets_from_vault.py
	@docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

prod: ## Run docker compose with prod environment
	@echo "⏳ Loading secrets from Vault and starting production environment..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

prod-build: ## Build and run docker compose with prod environment
	@echo "⏳⚙️ Loading secrets from Vault and building production environment..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

down: ## Stop all containers
	@echo "🛑 Stopping all containers..."
	docker-compose down --volumes --remove-orphans

down-clean: ## Stop all containers and remove volumes
	@echo "🛑 Stopping all containers and removing volumes..."
	docker-compose down --volumes --remove-orphans
	@echo "🧹 Removing environment file..."
	rm -fv .env
	@echo "🧹 Removing Terraform state and lock files..."
	rm -rfv $(TF_DIR)/vault/.terraform $(TF_DIR)/vault/.terraform.lock.hcl $(TF_DIR)/vault/terraform.tfstate*

restart-dev: ## Restart development environment
	@echo "🔄 Restarting development environment..."
	make down
	make dev

restart-prod: ## Restart production environment
	@echo "🔄 Restarting production environment..."
	make down
	make prod

logs: compose-logs
compose-logs:
	@echo "🔍 Viewing logs for all services..."
	@docker-compose logs -f

logs-api: ## View API logs
	@echo "🔍 Viewing API logs..."
	docker-compose logs -f api

logs-traefik: ## View Traefik logs
	@echo "🔍 Viewing Traefik logs..."
	docker-compose logs -f traefik

logs-to-file: ## Save logs from all containers to timestamped files in logs/docker directory
	@mkdir -p logs/docker
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	echo "💾 Saving all container logs to logs/docker/all_containers_$${timestamp}.log"; \
	docker-compose logs > logs/docker/all_containers_$${timestamp}.log; \
	echo "💾 Saving API logs to logs/docker/api_$${timestamp}.log"; \
	docker-compose logs api > logs/docker/api_$${timestamp}.log; \
	echo "💾 Saving Traefik logs to logs/docker/traefik_$${timestamp}.log"; \
	docker-compose logs traefik > logs/docker/traefik_$${timestamp}.log; \
	echo "💾 Saving Celery logs to logs/docker/celery_$${timestamp}.log"; \
	docker-compose logs celery-worker > logs/docker/celery_$${timestamp}.log; \
	echo "💾 Saving Redis logs to logs/docker/redis_$${timestamp}.log"; \
	docker-compose logs redis > logs/docker/redis_$${timestamp}.log; \
	echo "💾 Saving all logs to logs/docker/txt/all_containers_$${timestamp}.log.txt"; \
	cp logs/docker/all_containers_$${timestamp}.log logs/docker/txt/all_containers_$${timestamp}.log.txt; \
	echo "✅ All logs saved to logs/docker/ directory with timestamp $${timestamp}"

logs-aggregated: ## Save all logs to a single aggregated file (aggregated.log)
	@mkdir -p logs/docker
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	@echo "💾 Saving all container logs to logs/docker/aggregated_$${timestamp}.log"; \
	docker-compose logs > logs/docker/aggregated_$${timestamp}.log; \
	echo "✅ All logs saved to logs/docker/aggregated_$${timestamp}.log"

logs-watch: ## Continuously update the aggregated log file (run in background)
	@mkdir -p logs/docker
	@echo "🔄 Starting watch on container logs, saving to logs/docker/aggregated.log"; \
	while true; do \
		docker-compose logs --tail=100 > logs/docker/aggregated.log; \
		sleep 10; \
	done

archive-logs: ## Archive logs
	@echo "📦 Archiving logs..."
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	archive_name="logs/docker-$${timestamp}.tar.zst"; \
	find logs/docker -type f -name '*.log' > logs_to_archive.txt; \
	tar --files-from=logs_to_archive.txt -I 'zstd -19 -T0' -cf "$${archive_name}"; \
	echo "🗑️  Deleting archived files..."; \
	xargs rm -v < logs_to_archive.txt; \
	rm logs_to_archive.txt; \
	echo "✅ Archive created: $${archive_name}"


prune: ## Prune unused Docker resources
	@echo "🧹 Pruning unused Docker resources..."
	docker system prune -f

flush-cache: ## Clear Redis cache for metadata
	@echo "🧹 Flushing Redis cache..."
	@docker exec -i $$(docker ps -q -f name=grimwaves-api_redis_1) redis-cli FLUSHDB
	@echo "✅ Redis cache cleared"

certs: ## Generate self-signed certificates for local development
	@echo "🔐 Generating self-signed certificates for local development..."
	cd traefik && ./generate-cert.sh && cd ..

check-vault-agent:
	@if [ -z "$$(docker ps -q -f name=vault-agent)" ]; then \
		echo "🚨 Vault Agent container is not running!"; \
		echo "👉 Run 'make dev' or 'make compose-up'"; \
		exit 1; \
	else \
		echo "✅ Vault Agent container is running."; \
	fi

compose-build:
	@docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

compose-up:
	@docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d


# check-vault-agent-socket:
# 	@if [ ! -S "vault-agent/sock/vault.sock" ]; then \
# 		echo "🚨 Vault Agent socket file does not exist!"; \
# 		echo "👉 Run 'make dev' or 'make compose-up'"; \
# 		exit 1; \
# 	else \
# 		echo "✅ Vault Agent socket file exists."; \
# 	fi



# ================= Vault / Terraform ====================

TF_DIR=.cicd/terraform
KEY_FILE=~/Projects/learn-vault-docker-lab/.vault_docker_lab_1_init
UNSEAL_KEY=$$(grep 'Unseal Key 1' $(KEY_FILE) | awk '{print $$NF}')
ROOT_TOKEN=$$(grep 'Root Token' $(KEY_FILE) | awk '{print $$NF}')

# Define variables using Make's recursive expansion assignment (=)
# This defers the execution of the shell commands until the variables are actually used.
# IMPORTANT: These must NOT be indented.
VAULT_ROLE_ID = $(shell cd .cicd/terraform/vault && terraform output -raw role_id)
VAULT_SECRET_ID = $(shell cd .cicd/terraform/vault && terraform output -raw secret_id)
# WRAPPED_SECRET_ID = $(shell cd .cicd/terraform/vault && terraform output -json wrapped_secret_id_token | jq -r '.')

# # Vault
# vault: ## Initialize Vault, login with root token, apply Terraform configuration, and save development token
# 	make vault-init
# 	make vault-apply
# 	make vault-gen-env

# Vault
vault: ## Initialize Vault, login with root token, apply Terraform configuration, and save development token
	make vault-init
	make vault-apply

	# make vault-init
	# make vault-login-root
	# make vault-apply
	# make vault-token-save	
	# make vault-gen-env

vault-gen-env:
	@echo "⏳ Generating vault secret files..."
	@mkdir -p vault-agent/sock # Ensure directory exists
	@echo -n "${VAULT_ROLE_ID}" > vault-agent/sock/role_id
	@echo -n "${VAULT_SECRET_ID}" > vault-agent/sock/secret_id
	@echo "✅ Vault secret files successfully created."

vault-unseal: ## Unseal Vault
	@echo "🔓 Unsealing Vault..." 
	vault operator unseal $(UNSEAL_KEY)

vault-init: ## Initialize Terraform
	@echo "🔑 Initializing Vault..."
	cd $(TF_DIR)/vault && terraform init

vault-apply: ## Apply Terraform configuration
	make vault-test-connection
	@echo "🔑 Applying Terraform configuration..."
	cd $(TF_DIR)/vault && VAULT_SKIP_VERIFY=$(VAULT_SKIP_VERIFY) terraform apply \
		-var="vault_address=$(VAULT_ADDR)" \
		-var="vault_token=$(VAULT_TOKEN)" \
		$(if $(SPOTIFY_CLIENT_ID),-var="spotify_client_id=$(SPOTIFY_CLIENT_ID)") \
		$(if $(SPOTIFY_CLIENT_SECRET),-var="spotify_client_secret=$(SPOTIFY_CLIENT_SECRET)") \
		-auto-approve

vault-plan: ## Plan Terraform configuration
	@echo "🔑 Planning Terraform configuration..."
	cd $(TF_DIR)/vault && terraform plan

vault-policy-show: ## Show Vault policy in CLI
	@echo "🔑 Showing Vault policy in CLI..."
	cd $(TF_DIR)/vault && terraform output -raw vault_policy_name

vault-token-create: ## Create dev-token with grimwaves-dev policy
	@echo "🔐 Creating Vault token with policy grimwaves-dev..."
	@vault token create -policy="grimwaves-dev" -ttl=24h -format=json | jq -r .auth.client_token > ~/.vault-token
	@echo "✅ Token saved to ~/.vault-token"
	@make vault-login

vault-token-show: ## Show Vault token in CLI
	@echo "🔑 Showing Vault token in CLI..."
	cd $(TF_DIR)/vault && terraform output -raw vault_token

vault-token-check: ## Check Vault token
	@echo "🔍 Checking Vault token..."
	@vault token lookup || (echo "❌ Token is invalid" && exit 1)

vault-token-save: ## Save Vault token to .vault-token
	@echo "🔑 Logging in with AppRole and saving token..."
	@vault write -format=json auth/grimwaves-approle/login \
	  role_id=$(VAULT_ROLE_ID) \
	  secret_id=$(VAULT_SECRET_ID) | jq -r .auth.client_token > ~/.vault-token
	make vault-login

vault-login: ## Login using saved token
	@echo "🔑 Logging in to Vault using saved token..."
	vault login $$(cat ~/.vault-token)

vault-login-root: ## Login to Vault using ROOT_TOKEN=<token>
	@echo "🔐 Logging in with root token..."
	echo $(ROOT_TOKEN)
	vault login $(ROOT_TOKEN)

vault-token-revoke: ## Revoke saved token (⚠️  remove token, be careful)
	make vault-test-connection
	@echo "🔑 Revoking saved token..."
	vault token revoke $$(cat ~/.vault-token)
	rm -f ~/.vault-token

vault-token-load: ## Load Vault token from .vault-token
	@echo "🔑 Loading Vault token from .vault-token..."
	vault login $$(cat ~/.vault-token)

vault-destroy: ## Destroy Terraform configuration
	make vault-test-connection
	@echo "🔑 Destroying Terraform configuration..."
	cd $(TF_DIR)/vault && VAULT_SKIP_VERIFY=$(VAULT_SKIP_VERIFY) terraform destroy \
		-var="vault_address=$(VAULT_ADDR)" \
		-var="vault_token=$(VAULT_TOKEN)" \
		$(if $(SPOTIFY_CLIENT_ID),-var="spotify_client_id=$(SPOTIFY_CLIENT_ID)") \
		$(if $(SPOTIFY_CLIENT_SECRET),-var="spotify_client_secret=$(SPOTIFY_CLIENT_SECRET)") \
		-auto-approve

vault-destroy-clean: ## Destroy Terraform configuration and clean up	
	make vault-test-connection
	@echo "🔑 Destroying Terraform configuration and cleaning up..."
	make vault-destroy
	make vault-clean

vault-destroy-clean-all: ## Destroy Terraform configuration and clean up	
	make vault-test-connection
	@echo "🔑 Destroying Terraform configuration and cleaning up..."
	make vault-destroy
	make vault-clean
	make vault-agent-clean

vault-clean: ## Clean up Vault
	@read -p "⚠️  This will remove all Vault configuration. Are you sure you want to clean up Vault? (y/n): " confirm; \
	if [ "$$confirm" != "y" ]; then \
		echo "🚫 Cleanup cancelled"; \
		exit 1; \
	fi; \
	echo "🧹  Cleaning up Vault configuration..."; \
	rm -rfv $(TF_DIR)/vault/.terraform $(TF_DIR)/vault/.terraform.lock.hcl $(TF_DIR)/vault/terraform.tfstate* $(TF_DIR)/vault/.terraform.tfstate.lock.info

vault-agent-clean: ## Clean up Vault Agent configuration
	read -p "⚠️  This will remove all Vault Agent configuration. Are you sure you want to clean up Vault Agent? (y/n): " confirm; \
	if [ "$$confirm" != "y" ]; then \
		echo "🚫 Cleanup cancelled"; \
		exit 1; \
	fi; \
	@echo "🧹  Cleaning up Vault Agent configuration..."; \
	rm -fv .env; \
	rm -fv vault-agent/auth/role-id; \
	rm -fv vault-agent/auth/secret-id; \
	rm -fv vault-agent/token/vault-token; \
	rm -fv vault-agent/sockets/agent.sock; \
	rm -fv vault-agent/rendered/.env; \
	rm -fv vault-agent/config/agent.hcl;


# Compute
compute-init: ## Initialize Terraform
	@echo "🔑 Initializing Terraform for compute..."
	cd $(TF_DIR)/compute && terraform init

compute-apply: ## Apply Terraform configuration
	@echo "🔑 Applying Terraform configuration for compute..."
	cd $(TF_DIR)/compute && terraform apply -auto-approve

compute-plan: ## Plan Terraform configuration
	@echo "🔑 Planning Terraform configuration for compute..."
	cd $(TF_DIR)/compute && terraform plan

compute-destroy: ## Destroy Terraform configuration
	@echo "🔑 Destroying Terraform configuration for compute..."
	cd $(TF_DIR)/compute && terraform destroy -auto-approve


# ==============================================================================
# SECURITY CHECKS
# ==============================================================================
.PHONY: check-vulns
check-vulns: ## Check for vulnerabilities in Python dependencies using Safety
	@echo "🛡️  Checking for vulnerabilities in Python dependencies..."
	@echo "n" | poetry run safety scan --disable-optional-telemetry --continue-on-error || \
	  (echo "🔒 Safety scan found vulnerabilities or an error occurred. See details above." && exit 1)

.PHONY: check-code-security
check-code-security: ## Check for code security vulnerabilities using Bandit
	@echo "🛡️  Checking for code security vulnerabilities..."
	poetry run bandit -r grimwaves_api/

.PHONY: scan-config
scan-config: ## Scan configuration files for misconfigurations using Trivy
	@echo "🛡️  Scanning configuration files (Dockerfile, docker-compose, Terraform)..."
	@docker run --rm -v $$(pwd):/scan-target -w /scan-target \
	  aquasec/trivy:latest \
	  config --exit-code 1 --severity HIGH,CRITICAL -q /scan-target
	@echo "✅ Config scanning complete. No HIGH or CRITICAL misconfigurations found."

.PHONY: scan-images-dev
scan-images-dev: ## Scan built/used Docker images for vulnerabilities using Trivy (dynamically finds images)
	@echo "🛡️  Scanning Docker images for vulnerabilities..."
	overall_status=0; \
	images_to_scan=$$(docker-compose -f docker-compose.yml -f docker-compose.dev.yml config --images); \
	echo "Images to scan: $$images_to_scan"; \
	mkdir -p .cache/trivy; \
	for image in $$images_to_scan; do \
			echo "--> Scanning $$image..."; \
			docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
				-v $$(pwd)/.cache/trivy:/root/.cache/ \
				-v $$(pwd):/scan-target -w /scan-target \
				aquasec/trivy:latest \
				image --exit-code 1 --ignore-unfixed --severity HIGH,CRITICAL --no-progress $$image || overall_status=1; \
	 done; \
	if [ $$overall_status -ne 0 ]; then \
			echo "🔥 Vulnerabilities found in one or more images!"; \
			exit 1; \
	 else \
			echo "✅ Image scanning complete. No HIGH or CRITICAL vulnerabilities found."; \
	 fi


# ==============================================================================
# VAULT SECRET ID ROTATION
# ==============================================================================
.PHONY: vault-rotate-secret-id
vault-rotate-secret-id: ## Rotate the Vault AppRole Secret ID and restart the agent. Verify by checking `ls -l vault-agent/auth/secret-id` (timestamp) and `docker logs vault-agent` (successful auth).
	@echo "🔑 Rotating Vault AppRole Secret ID..."
	@cd .cicd/terraform/vault && \
	echo "   - Tainting Secret ID resource in Vault..." && \
	terraform taint vault_approle_auth_backend_role_secret_id.agent_secret_id && \
	echo "   - Tainting Secret ID file resource..." && \
	terraform taint local_sensitive_file.secret_id_file && \
	echo "   - Applying Terraform changes (will recreate tainted resources)..." && \
	terraform apply -auto-approve && \
	cd ../../..
	@echo "🔄 Restarting Vault Agent to use the new Secret ID..."
	@docker-compose restart vault-agent
	@echo "✅ Vault Secret ID rotated and agent restarted successfully."


.PHONY: help
help: ## Display help for available make targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: vault-check-env

vault-check-env: ## Check if required Vault environment variables are set
	@echo "🔍 Checking required Vault environment variables..."
	@if [ -z "$(VAULT_ADDR)" ]; then \
		echo "❌ Error: VAULT_ADDR is not set"; \
		echo "   Please set it with: export VAULT_ADDR=https://your-vault-server:8200"; \
		exit 1; \
	fi
	@if [ -z "$(VAULT_TOKEN)" ]; then \
		echo "❌ Error: VAULT_TOKEN is not set"; \
		echo "   Please set it with: export VAULT_TOKEN=your-token"; \
		echo "   Or run: vault login"; \
		exit 1; \
	fi
	@echo "✅ All required Vault environment variables are set:"
	@echo "   VAULT_ADDR = $(VAULT_ADDR)"
	@echo "   VAULT_TOKEN is set (value hidden for security)"

vault-test-connection: vault-check-env ## Test connection to Vault server
	@echo "🔍 Testing connection to Vault server at $(VAULT_ADDR)..."
	@if vault status >/dev/null 2>&1; then \
		echo "✅ Successfully connected to Vault server"; \
	else \
		echo "❌ Failed to connect to Vault server at $(VAULT_ADDR)"; \
		echo "   Please check your network connection and Vault server status."; \
		exit 1; \
	fi

vault-get-github-credentials: vault-test-connection ## Получить Role ID и Secret ID для GitHub Actions
	@echo "🔐 Получение учетных данных для GitHub Actions..."
	@echo "⚠️ Сохраните эти данные как секреты в GitHub Actions ⚠️"
	@echo "-------------------------------------------"
	@echo "VAULT_ADDR: $(VAULT_ADDR)"
	@echo "VAULT_ROLE_ID: $(VAULT_ROLE_ID)"
	@echo "-------------------------------------------"
	@echo "Опции:"
	@echo "1) Использовать текущий Secret ID (действителен еще $(shell echo $$((604800/86400))) дней):"
	@echo ""
	@echo "2) Получить новый Secret ID:"
	@echo "   make vault-rotate-secret-id && make vault-get-github-credentials"
	@echo "-------------------------------------------"
	@echo "✅ Готово! Скопируйте эти значения в GitHub Secrets"
