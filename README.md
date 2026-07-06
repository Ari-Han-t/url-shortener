# Distributed URL Shortener

A highly scalable, production-ready URL shortener built with FastAPI, PostgreSQL, Redis, Nginx, and Docker. 

This project demonstrates advanced backend engineering concepts including connection pooling, caching strategies, background task processing, rate limiting, and horizontal scaling via a reverse proxy load balancer.

## System Architecture

- **Web Framework:** FastAPI (Python)
- **Database:** PostgreSQL (with `psycopg2` Connection Pooling)
- **Caching & Rate Limiting:** Redis
- **Reverse Proxy / Load Balancer:** Nginx
- **Containerization:** Docker & Docker Compose

### Features
1. **JWT Authentication:** Secure user registration and login endpoints.
2. **URL Shortening:** Generate custom or randomized short aliases for long URLs.
3. **Analytics Tracking:** Clicks are tracked securely with IP address and User-Agent logging.
4. **Cache-Aside Pattern:** High-frequency redirects hit Redis first (Cache Hit). If missing, they fallback to Postgres and update the cache (Cache Miss).
5. **Background Delegation:** Click analytics (Postgres INSERTs/UPDATEs) are delegated to FastAPI BackgroundTasks to ensure zero added latency to the user's redirect.
6. **Rate Limiting:** IP-based request throttling using `slowapi` to prevent abuse.
7. **QR Code Generation:** Dynamic generation of QR codes for shortened URLs.

## Quick Start (Local Setup)

1. Clone the repository.
2. Rename `.env.example` to `.env` and fill in your secure passwords and secrets.
3. Make sure you have Docker Desktop installed and running.
4. Run the following command in the root directory to spin up the entire distributed system (1 Nginx Load Balancer, 3 FastAPI Replicas, 1 Postgres DB, 1 Redis Cache):

```bash
docker compose up -d --scale web=3 --build
```

5. Access the interactive API documentation at:
   `http://localhost/docs`

6. To view the Load Balancer in action, spam refresh on the `/docs` page and run:
```bash
docker compose logs web
```
You will see `web-1`, `web-2`, and `web-3` seamlessly taking turns handling your requests!
