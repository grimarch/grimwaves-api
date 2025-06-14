#!/bin/bash
set -euxo pipefail # Halt on error and undefined variables

export DEBIAN_FRONTEND=noninteractive

# --- BEGIN INJECTED NETWORK UTILS ---
# shellcheck disable=SC2154  # network_utils_content injected by Terraform
${network_utils_content}
# --- END INJECTED NETWORK UTILS ---

# --- BEGIN INJECTED DOCKER UTILS ---
# shellcheck disable=SC2154  # docker_utils_content injected by Terraform  
${docker_utils_content}
# --- END INJECTED DOCKER UTILS ---

# --- BEGIN INJECTED AGENT UTILS ---
# shellcheck disable=SC2154  # agent_utils_content injected by Terraform
${agent_utils_content}
# --- END INJECTED AGENT UTILS ---

# --- Main script execution ---

# Perform network checks first
perform_network_checks

# System updates and essential packages
echo "Starting system updates and package installation..."
apt-get update -yq
apt-get install -yq curl unzip jq tree vim net-tools dnsutils docker.io docker-compose glances htop ncdu ca-certificates software-properties-common fail2ban make
echo "✅ Essential packages (including docker.io) installed."

# Add HashiCorp GPG key
echo "Adding HashiCorp GPG key..."
wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null
echo "✅ HashiCorp GPG key added."

# Add HashiCorp repository
echo "Adding HashiCorp repository..."
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/hashicorp.list
echo "✅ HashiCorp repository added."

# Update package list again and install Vault
echo "Updating package list and installing Vault..."
apt-get update -yq
apt-get install -yq vault
echo "✅ Vault installed."

echo "✅ Finished system updates and package installation (including Vault)."

# Configure Fail2ban for SSH protection
echo "Configuring Fail2ban for SSH protection..."
# shellcheck disable=SC2154  # ssh_port is Terraform template variable
cat > /etc/fail2ban/jail.local << EOL
[sshd]
enabled = true
port = ${ssh_port}  # ssh_port injected by Terraform
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
bantime = 3600
findtime = 600
EOL
systemctl enable fail2ban
systemctl restart fail2ban
echo "✅ Fail2ban configured and started for SSH protection."

# Configure SSH to use non-standard port and enhance security
echo "Configuring SSH security settings..."
# shellcheck disable=SC2154  # ssh_port injected by Terraform
sed -i "s/#Port 22/Port ${ssh_port}/" /etc/ssh/sshd_config
sed -i "s/^#*PermitRootLogin.*/PermitRootLogin no/" /etc/ssh/sshd_config
sed -i "s/#PasswordAuthentication yes/PasswordAuthentication no/" /etc/ssh/sshd_config
sed -i "s/#MaxAuthTries 6/MaxAuthTries 6/" /etc/ssh/sshd_config  # Keep default 6 for Agent compatibility

# Configure DigitalOcean Agent for custom SSH port
configure_do_agent "${ssh_port}"

# Restart SSH first, then Agent (proper order)
systemctl restart sshd
echo "✅ SSH configured to use port ${ssh_port} with enhanced security."

# Restart and verify DigitalOcean Agent
restart_and_verify_do_agent "$AGENT_SERVICE_UPDATED"

# Create deploy user for secure deployment
echo "Creating deploy user for deployment..."
# Create user with home directory and bash shell
useradd -m -s /bin/bash deploy

# Add SSH authorized keys for deploy (copy from root)
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Configure sudo access for deploy
cat > /etc/sudoers.d/deploy << EOL
# Allow deploy to execute all commands without password
deploy ALL=(ALL) NOPASSWD:ALL
EOL
chmod 440 /etc/sudoers.d/deploy

# Add deploy to necessary groups
usermod -aG docker deploy
usermod -aG systemd-journal deploy

echo "✅ deploy user created with sudo privileges."

# Docker post-installation steps
echo "Configuring Docker group for 'ubuntu' and 'root' users..."
usermod -aG docker ubuntu || echo "[Warning] User 'ubuntu' not found, skipping add to docker group."
if id -u "root" >/dev/null 2>&1; then
    usermod -aG docker root || echo "[Warning] Failed to add 'root' to docker group."
fi
echo "✅ Docker group configuration attempted."
# Note: A logout/login or newgrp docker is needed for group changes to apply to current shell.
# For services/scripts started after this, it should be fine.

# --- Docker Setup using injected functions ---
ensure_docker_installed_and_running
configure_docker_dns

# Also configure system DNS to use the same servers (backup solution)
echo "Configuring system DNS resolution to match firewall rules..."
cat > /etc/systemd/resolved.conf << EOF
[Resolve]
DNS=67.207.67.2 67.207.67.3 67.207.67.4 8.8.8.8 1.1.1.1
FallbackDNS=8.8.4.4 1.0.0.1
Domains=
DNSSEC=yes
DNSOverTLS=no
MulticastDNS=yes
LLMNR=yes
Cache=yes
CacheFromLocalhost=no
EOF

echo "Restarting systemd-resolved and Docker service to apply DNS configuration..."
systemctl restart systemd-resolved
systemctl restart docker
sleep 5
echo "✅ Both system DNS and Docker DNS configured and restarted."
verify_docker_setup
test_docker_dns
# --- End of Docker Setup ---

echo "✅ Docker successfully configured and verified."

# Create directory structure for GrimWaves API
echo "Creating directory structure for GrimWaves API..."
# shellcheck disable=SC2154  # project_name injected by Terraform
mkdir -p /var/app/"${project_name}"/{logs,data}
mkdir -p /var/app/"${project_name}"/vault-agent/{auth,token,rendered,templates,sockets}

# Set correct permissions for app directory
chown -R 1000:1000 /var/app/"${project_name}"
echo "✅ GrimWaves API directories created."

# Mount volume for persistent data storage
echo "Setting up persistent data volume..."
if [ ! -d "/mnt/data" ]; then
    mkdir -p /mnt/data
fi

# Mount the volume (environment and project_name injected by Terraform)
# shellcheck disable=SC2154  # environment injected by Terraform
mount /dev/disk/by-id/scsi-0DO_Volume_"${project_name}"-"${environment}"-data /mnt/data
echo "/dev/disk/by-id/scsi-0DO_Volume_${project_name}-${environment}-data /mnt/data ext4 defaults,nofail,discard 0 0" >> /etc/fstab

# Create subdirectories for different services
mkdir -p /mnt/data/{redis,logs,backups}

# Set proper ownership and permissions
chown -R 1000:1000 /mnt/data
chmod -R 755 /mnt/data

# For Redis specifically (needs restrictive permissions)
chmod 700 /mnt/data/redis
echo "✅ Persistent data volume configured."

# Set hostname for the server
# shellcheck disable=SC2154  # environment and project_name injected by Terraform
hostnamectl set-hostname "${project_name}"-"${environment}"
echo "✅ Hostname set to ${project_name}-${environment}."

# Signal that cloud-init basic setup (dirs, packages) has finished
echo "✅ Cloud-init script (packages and directories) finished successfully."
touch /tmp/cloud_init_done 