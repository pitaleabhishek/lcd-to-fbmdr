# Dependency register

The app pins versions in `pyproject.toml` and `uv.lock`. The Docker image runs
`uv sync --frozen --no-dev`.

## Runtime

| Component | Version | Licence | Purpose | Maintenance |
|---|---|---|---|---|
| Python | 3.12 | PSF-2.0 | Runtime | Security fixes to 2028 |
| Django | 5.2.19 | BSD-3-Clause | Web framework | Active LTS to 2028 |
| gunicorn | 26.2.0 | MIT | Hosted WSGI server | Active |
| psycopg | 3.3.8 | LGPL-3.0-only | PostgreSQL driver | Active |
| PostgreSQL | 17 | PostgreSQL Licence | JSON data and triggers | Supported to 2029 |
| Caddy | 2 | Apache-2.0 | Optional HTTPS | Active |
| OpenSSL | 3.x | Apache-2.0 | Certificates and backups | Active |

## Development and test

| Component | Version | Licence | Purpose | Maintenance |
|---|---|---|---|---|
| uv | 0.10.0 | Apache-2.0 OR MIT | Lockfile installs | Active |
| pytest | 9.2.0 | MIT | Tests | Active |
| pytest-django | 4.14.0 | BSD-3-Clause | Django test support | Active |
| pytest-xdist | 3.8.0 | MIT | Parallel tests | Active |

The app does not use transitive packages directly.
