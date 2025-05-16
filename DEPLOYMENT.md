# Deployment Guide for GrimWaves API

This document provides instructions for deploying GrimWaves API to a production environment.

## Prerequisites

- A Linux server (Ubuntu 22.04 LTS or newer recommended)
- Docker and Docker Compose installed
- Domain name with DNS configured to point to your server
- DuckDNS account for free SSL certificates

## Preparation

### 1. Set up your server

Install Docker and Docker Compose:

```bash
# Update packages
sudo apt update
sudo apt upgrade -y

# Install required packages
sudo apt install -y curl git make

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to the docker group
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin
```

Log out and log back in for group changes to take effect.

### 2. Clone the repository

```bash
git clone https://github.com/yourusername/grimwaves-api.git
cd grimwaves-api
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit the `.env` file with your production settings:

```
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=info
DUCKDNS_TOKEN=your_duckdns_token
DUCKDNS_DOMAIN=your_domain.duckdns.org
```

### 4. Set up Traefik for HTTPS

#### Using DuckDNS (Recommended)

1. Register at [DuckDNS](https://www.duckdns.org) and create a subdomain
2. Copy your token and domain name to the `.env` file

```
DUCKDNS_TOKEN=your_token_here
DUCKDNS_DOMAIN=your_domain.duckdns.org
```

#### Using Let's Encrypt with HTTP Challenge (Alternative)

If you prefer using HTTP challenge, modify the `traefik/traefik.yml` file to use the HTTP challenge:

```yaml
certificatesResolvers:
  letsencrypt:
    acme:
      email: your-email@example.com
      storage: /etc/traefik/acme.json
      httpChallenge:
        entryPoint: web
```

And update the `docker-compose.prod.yml` file to use this resolver.

## Deployment

### 1. Start the application

```bash
make prod
```

This will:
- Build the Docker containers
- Configure Traefik with Let's Encrypt certificates
- Start all services in production mode

### 2. Verify the deployment

Your application should now be accessible at:

- API: `https://yourdomain.duckdns.org`
- Traefik Dashboard: `https://traefik.yourdomain.duckdns.org` (protected with basic auth)

## Maintenance

### Viewing logs

```bash
# View all logs
make logs

# View API logs only
make logs-api

# View Traefik logs only
make logs-traefik
```

### Updating the application

```bash
# Pull latest changes
git pull

# Restart with changes
make restart-prod
```

### Backups

It's recommended to set up automated backups for your data:

```bash
# Manual backup
docker-compose stop
tar -czf backup-$(date +%Y%m%d).tar.gz data logs
docker-compose start
```

You can add this to a cron job for automated backups.

## Security Considerations

1. **Firewall**: Configure a firewall to allow only ports 80, 443, and your SSH port
2. **SSH**: Disable password authentication and use key-based auth only
3. **Updates**: Keep your system and Docker up to date
4. **Monitoring**: Set up monitoring for your services (e.g., Prometheus and Grafana)

## Troubleshooting

### Certificate issues

If you encounter issues with Let's Encrypt certificates:

1. Check Traefik logs: `make logs-traefik`
2. Verify DuckDNS settings in your `.env` file
3. Reset acme.json: `rm traefik/acme.json && touch traefik/acme.json && chmod 600 traefik/acme.json`
4. Restart: `make restart-prod`

### Container not starting

If a container fails to start:

1. Check container logs: `docker-compose logs api`
2. Verify environment variables
3. Try rebuilding: `docker-compose build api`

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [DuckDNS Documentation](https://www.duckdns.org/faqs.jsp) 