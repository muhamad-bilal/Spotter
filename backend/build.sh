#!/usr/bin/env bash
# Render build script. Paste `bash build.sh` into Render's Build Command with
# the service's Root Directory set to `backend`.
set -o errexit

pip install -r requirements.txt

# Admin + DRF assets, served by whitenoise.
python manage.py collectstatic --noinput

# SQLite lives on Render's ephemeral disk: this recreates the schema on every
# deploy. Saved trips are demo records and reset on restart -- documented.
python manage.py migrate

# Optional: create an admin login when the DJANGO_SUPERUSER_* env vars are set.
# Idempotent -- the || true keeps redeploys from failing once the user exists.
if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" ]]; then
  python manage.py createsuperuser --noinput || true
fi
