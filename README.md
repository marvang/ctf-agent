# Kali Machine with Docker Compose

This project uses Docker Compose to run a Kali Linux container.
This project uses uv instead of pip.

---

## Usage

### 1. Build and start the container

docker compose up -d
-d means it runs in the background.
## 2. Enter the Kali machine
docker compose exec kali bash
## 3. Exit the Kali machine
exit
## 4. Stop the container
docker compose down
