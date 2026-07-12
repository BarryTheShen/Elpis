# Elpis Docker image

Elpis runs as one application container on port `8899`. The container includes
the Python backend and built Preact frontend; it does not bundle Ollama or run
the digest worker on a separate public port.

## Build and run

```bash
git clone git@github.com:BarryTheShen/Elpis.git
cd Elpis
cp config.example.yaml config.yaml
cp .env.example .env
docker compose up -d --build
```

Open [http://localhost:8899](http://localhost:8899). Stop the stack with:

```bash
docker compose down
```

## Image configuration

[`docker-compose.yml`](../docker-compose.yml) builds and tags `elpis:latest`
by default:

```yaml
image: ${ELPIS_IMAGE:-elpis:${ELPIS_IMAGE_TAG:-latest}}
```

An operator publishing an Elpis image to a controlled registry can override the
tag without changing Compose:

```bash
export ELPIS_IMAGE=registry.example/elpis
export ELPIS_IMAGE_TAG=1.0.0
docker compose build
docker compose push
```

Never substitute an upstream CondenseIt image for an Elpis deployment.

## Health and persistent data

The Compose health check requests `/health`. The application returns success
only after its SQLite store accepts a read query; storage failures return HTTP
503. Compose mounts these operator-owned paths:

- `config.yaml`: feeds, provider configuration, schedule, and access settings
- `./data/`: SQLite database and generated publication files

Back up `./data/` before upgrades or migrations.

## Attribution

Elpis is independently released and retains CondenseIt's upstream history and
original MIT license. Keep CondenseIt configured as `upstream`; publish only
Elpis-owned image tags and releases.
