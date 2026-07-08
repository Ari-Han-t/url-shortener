# Distributed URL Shortener

A highly scalable, production-ready, and highly secure URL shortener built with FastAPI, React, PostgreSQL, Redis, Nginx, and Docker. 

This project demonstrates advanced backend engineering and DevSecOps concepts including connection pooling, caching strategies, background task processing, rate limiting, and robust application security.

## System Architecture

- **Frontend:** React + Vite, styled with Tailwind CSS and Framer Motion.
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL (with `psycopg2` Connection Pooling)
- **Caching & Rate Limiting:** Redis
- **Reverse Proxy / Load Balancer:** Nginx
- **Containerization:** Docker & Docker Compose (Multi-stage builds)

### Features & Security Hardening
1. **JWT Authentication:** Secure user registration and login endpoints via OAuth2 scopes.
2. **URL Shortening:** Generate custom or randomized short aliases for long URLs.
3. **Analytics Tracking:** Clicks are tracked securely with IP address and User-Agent logging.
4. **Cache-Aside Pattern:** High-frequency redirects hit Redis first (Cache Hit). If missing, they fallback to Postgres and update the cache (Cache Miss).
5. **Background Delegation:** Click analytics (Postgres INSERTs/UPDATEs) are delegated to FastAPI BackgroundTasks to ensure zero added latency to the user's redirect.
6. **Robust Rate Limiting:** IP-based request throttling using `slowapi` utilizing proper `X-Forwarded-For` header resolution to prevent brute-force and DDoS attacks.
7. **Strict Validation:** Reject dangerous URL schemes (`javascript:`, `data:`, `file:`) and validate payloads.
8. **Security Headers:** Enforced `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options`, and `X-Content-Type-Options` via custom middleware.
9. **Standardized API:** Consistent `{success: bool, data/message}` JSON API responses.
10. **Legal Compliance Ready:** Includes modular Privacy Policy, Terms of Service, Cookie Policy, and Disclaimer templates out of the box.

## Quick Start (Production Setup)

1. Clone the repository.
2. Rename `.env.example` to `.env` and fill in your secure passwords and secrets. **Do not commit your `.env` file!**
3. Ensure Docker and Docker Compose are installed.
4. Run the following command in the root directory to spin up the entire distributed system. The Dockerfile uses multi-stage builds to compile the React frontend and bundle it seamlessly with the FastAPI backend.

```bash
docker compose up -d --build
```

5. Access the application UI at: `http://localhost/` (or your server's IP address/domain).
6. Access the interactive API documentation at: `http://localhost/docs`

## Health Monitoring

The deployment includes an automated Docker HEALTHCHECK against the `/health` endpoint to ensure the application is responsive and healthy. You can verify container status with `docker ps`.
