# GrimWaves API

## Description
- FastAPI service that provides endpoints for servicing the GrimWaves channel
- Self-hosted solution using Docker, Traefik, and FastAPI

## Installation
```bash
# Install dependencies using Poetry
poetry install
```

## Development
```bash
# Run the development server locally
poetry run uvicorn grimwaves_api:app --reload

# Or using Docker Compose (recommended)
make dev
```

## API Documentation
Once the server is running, access the API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Technologies
- Python 3.13
- FastAPI 0.115.8
- Uvicorn 0.34.0
- Pydantic Settings
- Celery 5.5.1 (for asynchronous tasks)
- Redis 5.2.1 (for caching and task queue)
- Httpx 0.28.1 (for async HTTP requests)
- Docker & Docker Compose
- Traefik v3.3 (reverse proxy)

## Code Quality
- Ruff for linting and formatting
- MyPy for static type checking

## Project Structure
```
grimwaves-api/
├── grimwaves_api/      # Core application code
│   ├── __init__.py     # App initialization
│   ├── __main__.py     # Entry point
│   ├── core/           # Core functionality
│   │   ├── celery_app.py  # Celery configuration
│   │   └── settings.py    # Application settings
│   ├── modules/        # Feature modules
│   │   ├── music_metadata/  # Music metadata module
│   │   │   ├── clients/     # External API clients
│   │   │   ├── constants.py # Module constants
│   │   │   ├── router.py    # API endpoints
│   │   │   ├── schemas.py   # Data models
│   │   │   ├── service.py   # Business logic
│   │   │   ├── tasks.py     # Celery tasks
│   │   │   └── utils.py     # Helper functions
│   ├── common/         # Shared utilities
├── traefik/            # Traefik configuration files
├── data/               # Application data (mounted as volume)
├── logs/               # Application logs (mounted as volume)
├── docker-compose.yml  # Base Docker Compose configuration
├── docker-compose.dev.yml  # Development overrides
├── docker-compose.production.yml # Production overrides
├── Dockerfile          # Container definition
├── Makefile            # Helpful commands
└── README.md           # This file
```

## Async Resource Management

GrimWaves API provides robust asynchronous resource management through its `run_async_safely` utility, designed to handle event loops properly in multi-threaded environments like Celery workers:

### Key Features

- **Thread-Local Storage** for event loops, ensuring each thread has its own isolated event loop
- **Reference counting system** that only closes event loops when they're no longer in use
- **Synchronization with locks** to prevent concurrent access issues
- **Safe resource cleanup** with proper task cancellation and loop closure

### Benefits

- Prevents "Event loop is closed" errors in Celery tasks
- Eliminates "Task got Future attached to a different loop" errors
- Optimizes performance by reusing event loops within threads
- Prevents memory leaks from improperly managed async resources

For detailed documentation, see:
- [Developer Guide](/docs/run-async-safely-fix/developer_guide.md) - Comprehensive guide to the async resource management system

## Docker Setup
The application is containerized using Docker and uses Traefik as a reverse proxy.

### Available Make Commands

Run `make help` to see all available commands:

```
GrimWaves API - Makefile commands:

Usage: make [command]

Commands:
  dev            Start development environment
  prod           Start production environment
  down           Stop all containers
  down-clean     Stop all containers and remove volumes
  restart-dev    Restart development environment
  restart-prod   Restart production environment
  logs           View logs for all services
  logs-api       View API logs
  logs-traefik   View Traefik logs
  prune          Prune unused Docker resources
  certs          Generate self-signed certificates for local development
  help           Display this help message
```

### Development Setup
For local development with self-signed SSL certificates:

```bash
# Generate self-signed certificates
make certs

# Start development environment
make dev

# Access:
# - API via HTTPS: https://api.grimwaves.local/
# - Traefik Dashboard: https://traefik.grimwaves.local/dashboard/
```

Make sure to add the following entries to your `/etc/hosts` file:
```
127.0.0.1 api.grimwaves.local
127.0.0.1 traefik.grimwaves.local
127.0.0.1 grimwaves.local
```

### Production Setup
For production deployment with Let's Encrypt certificates:

```bash
# Set up your .env file with required credentials
# DUCKDNS_TOKEN and DUCKDNS_DOMAIN are required for Let's Encrypt

# Start production environment
make prod
```

### API Usage Examples

```bash
# Development environment (using self-signed certificates)
# Convert text to stylized format
curl -k -X POST "https://api.grimwaves.local/convert" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello", "style": "gothic"}'

# Fetch music release metadata - Submit task
curl -k -X POST "https://api.grimwaves.local/music/release_metadata" \
  -H "Content-Type: application/json" \
  -d '{"band_name": "Gojira", "release_name": "Fortitude", "country_code": "FR"}'

# Response:
# {"task_id":"sample-task-id","status":"queued"}

# Check task status and get results
curl -k -X GET "https://api.grimwaves.local/music/release_metadata/sample-task-id"

# Response:
# {"status":"pending","data":null,"error":null}

# Production environment (using Let's Encrypt certificates)
curl -X POST "https://grimwaves.duckdns.org/convert" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello", "style": "gothic"}'

# Fetch music release metadata - Submit task
curl -X POST "https://grimwaves.duckdns.org/music/release_metadata" \
  -H "Content-Type: application/json" \
  -d '{"band_name": "Gojira", "release_name": "Fortitude", "country_code": "FR"}'

# Check task status and get results
curl -X GET "https://grimwaves.duckdns.org/music/release_metadata/task-id-from-response"
```

## Music Metadata API

The `/music/release_metadata` endpoint provides metadata about music releases by searching across multiple music services:

- Information retrieved includes:
  - Artist details
  - Release information (name, date, label)
  - Track listing with ISRC codes
  - Genre information
  - Artist's social media links

- Available endpoints:
  - `POST /music/release_metadata` - Submit a metadata retrieval task
  - `GET /music/release_metadata/{task_id}` - Check status and retrieve results

- Data sources:
  - Spotify API
  - MusicBrainz API
  - Deezer API (as fallback)

## Security
- HTTPS enabled by default in both development and production
- Traefik dashboard protected by authentication
- Production uses Let's Encrypt certificates via DNS challenge
- HTTP automatically redirects to HTTPS
- Secure headers enforced in production

## Configuration
Environment variables are stored in the `.env` file:

```
ENVIRONMENT=development    # or production
DEBUG=true                 # or false in production
LOG_LEVEL=info             # or debug, warning, error
DUCKDNS_TOKEN=your_token   # Required for production
DUCKDNS_DOMAIN=your_domain # Required for production

# Celery and Redis settings
GRIMWAVES_CELERY_BROKER_URL=redis://redis:6379/0
GRIMWAVES_CELERY_RESULT_BACKEND=redis://redis:6379/0
GRIMWAVES_REDIS_URL=redis://redis:6379/1

# API Keys for music services
GRIMWAVES_SPOTIFY_CLIENT_ID=your_spotify_client_id
GRIMWAVES_SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
GRIMWAVES_MUSICBRAINZ_CONTACT=your_email@example.com
```

## TODO

- ✅ Implement docker-compose environment based on Traefik and FastAPI for local hosting
- ✅ Configure secure Traefik setup with TLS support
- ✅ Implement Celery + Redis for caching and background tasks
- ✅ Implement /release_metadata endpoint for retrieving release metadata by group name, release name, and optionally group country
- ✅ Improve asynchronous resource management to prevent "Event loop is closed" errors
- TODO: Implement CI/CD with docker-compose on Hetzner Cloud
- TODO: Implement PostgreSQL to store requested metadata
- TODO: Moving to CapRover/Coolify on Hetzner Cloud
