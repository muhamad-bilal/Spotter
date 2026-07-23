# Deploying

Two halves, deployed in this order: **backend to Render first** (you need its URL),
**then frontend to Vercel**, then one CORS value back on Render.

Both platforms deploy from GitHub, so push the repo first.

---

## 1. Backend → Render (free tier)

1. [dashboard.render.com](https://dashboard.render.com) → **New** → **Web Service**.
2. **Connect your GitHub repo**, pick this repository.
3. Fill the service form:

   | Field | Value |
   |---|---|
   | Name | `eld-trip-planner` (or anything — it becomes the URL) |
   | Language | **Python 3** |
   | Branch | `main` |
   | **Root Directory** | `backend` |
   | **Build Command** | `bash build.sh` |
   | **Start Command** | `gunicorn config.wsgi:application` |
   | Instance Type | **Free** |

4. **Environment variables** (Advanced → Add Environment Variable):

   | Key | Value | Why |
   |---|---|---|
   | `SECRET_KEY` | any long random string | Django signing key; never committed |
   | `GEOAPIFY_API_KEY` | your Geoapify key | routing — comes from Render env, **not** `.env` (the loader is a no-op when no `.env` file exists) |
   | `NOMINATIM_USER_AGENT` | `eld-trip-planner/1.0 (you@example.com)` | Nominatim policy requires it |
   | `PYTHON_VERSION` | `3.11.9` | match the version everything was tested on |
   | `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` / `DJANGO_SUPERUSER_EMAIL` | *(optional)* | build.sh creates the admin login for `/admin/` |

   Do **not** set `DEBUG` (it defaults to False) or `ALLOWED_HOSTS` /
   `CSRF_TRUSTED_ORIGINS` (the Render hostname is picked up automatically).

5. **Create Web Service** and watch the build: install → collectstatic → migrate.
6. Smoke-test: `https://<name>.onrender.com/api/trips/999999/` should return a
   JSON 404 (that's routing, hosts and DEBUG-off all working). `/admin/` should
   render with styling (that's whitenoise working).

---

## 2. Frontend → Vercel

1. [vercel.com/new](https://vercel.com/new) → **Import** the same repo.
2. Fill the project form:

   | Field | Value |
   |---|---|
   | **Root Directory** | `frontend` |
   | Framework Preset | **Vite** (auto-detected) |
   | Build Command | `npm run build` (default) |
   | Output Directory | `dist` (default) |

3. **Environment variable**:

   | Key | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://<name>.onrender.com` — your Render URL, no trailing slash |

   Locally this stays unset and the app falls back to `http://localhost:8000`.

4. **Deploy**. The build is a fully static bundle — no server code on Vercel.

---

## 3. Close the loop: CORS

1. Back on Render → your service → **Environment** → add:

   | Key | Value |
   |---|---|
   | `CORS_ALLOWED_ORIGINS` | `https://<project>.vercel.app` (comma-separate if you add preview URLs) |

2. Render restarts on env change. Then open the Vercel URL and plan a trip
   end-to-end: form → summary → map → log sheets → Download PDF.

---

## Operational notes

- **Cold starts.** The free Render instance spins down after ~15 minutes idle
  and takes **30–60 s** to wake. Hit the API once a few minutes **before any
  demo** so the first on-camera request isn't a spinner:
  `curl https://<name>.onrender.com/api/trips/999999/`
- **Trips reset on restart.** SQLite lives on Render's ephemeral filesystem —
  fine for demo records, but every deploy or restart starts with an empty
  database (and re-creates the superuser via the env vars, if set).
- **Nominatim rate limit.** Geocoding is throttled to 1 request/second, so a
  trip with three fresh addresses takes ~3 s before routing even starts.
- **Local dev is unchanged.** `backend/.env` sets `DEBUG=true`; production never
  reads that file. See README "Running it".
