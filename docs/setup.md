# Setup

This project is a prototype for the **Maternal Death Surveillance and Response
(MDSR)** workflow. It reuses the WHO **Labour Care Guide (LCG)** in the
**Facility-Based Maternal Death Review (FBMDR) Form 4**.

You need one prerequisite: Docker.

| System | Requirement |
|---|---|
| macOS 13 or later | Docker Desktop |
| Windows 10 or 11 | Docker Desktop with WSL2 |
| Linux | Docker Engine and the Compose plugin |
| Phone or locked-down computer | Use the hosted URL. No local install. |

Docker Desktop: https://www.docker.com/products/docker-desktop/

## One command

macOS and Linux:

```sh
./start.sh
```

Windows PowerShell:

```powershell
.\start.ps1
```

The script does these steps:

1. Checks Docker and Docker Compose.
2. Starts Postgres.
3. Waits until Postgres is ready.
4. Builds the app image.
5. Runs migrations.
6. Seeds the demo cases if they are absent.
7. Starts the web app.
8. Opens `http://127.0.0.1:8000`.

Run the command again whenever you want. It does not duplicate the demo cases.

## Log in

| User | Password | Role |
|---|---|---|
| `resident` | `resident123` | author |
| `fno` | `fno123` | approver |

## Stop and reset

Stop the app:

```sh
docker compose down
```

Reset all data and seed again:

```sh
docker compose down -v
./start.sh
```

`docker compose down -v` deletes the Postgres volume. Use it only for the demo.

## Manual setup

If you do not want the script:

```sh
docker compose up -d --build
docker compose exec web python manage.py demo_setup
```

Then open `http://127.0.0.1:8000`.

## Basic auth

Basic auth is optional. Set both variables to enable it:

```sh
BASIC_AUTH_USER=demo BASIC_AUTH_PASSWORD='a long password' ./start.sh
```

Or put them in an untracked `.env` file:

```text
BASIC_AUTH_USER=demo
BASIC_AUTH_PASSWORD=a long password
```

When both are set, the app asks for a browser HTTP login before any page loads.
Use it only with HTTPS. HTTP sends the password in clear text.

Set both variables or neither. The app will not start with only one.

## Hosted demo

The planned host name is:

```text
https://lcgtofbmdr.nirovia.in
```

The zone uses Cloudflare named tunnels. Do not add a public A record or a
Transform Rule. Create a separate tunnel:

```sh
cloudflared tunnel create lcgtofbmdr
cloudflared tunnel route dns --overwrite-dns lcgtofbmdr lcgtofbmdr.nirovia.in
```

Use a separate config. Do not reuse another tunnel or its credentials:

```yaml
tunnel: <tunnel-id>
credentials-file: /etc/cloudflared/<tunnel-id>.json

ingress:
  - hostname: lcgtofbmdr.nirovia.in
    service: http://127.0.0.1:8800
  - service: http_status:404
```

Run the tunnel as its own service. The app listens on `127.0.0.1:8800`. Set the
`.env` values:

```text
SECRET_KEY=a long random value
ALLOWED_HOSTS=lcgtofbmdr.nirovia.in
CSRF_TRUSTED_ORIGINS=https://lcgtofbmdr.nirovia.in
BASIC_AUTH_USER=demo
BASIC_AUTH_PASSWORD=a long password
```

Start the hosted stack:

```sh
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d --build db
docker compose -f docker-compose.yml -f docker-compose.deploy.yml build web
docker compose -f docker-compose.yml -f docker-compose.deploy.yml run --rm web \
  python manage.py demo_setup
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d web
```

Do not expose port 8800 to the public network. Keep it on `127.0.0.1`, and let
the reverse proxy handle public traffic. Do not commit the `.env` file.
