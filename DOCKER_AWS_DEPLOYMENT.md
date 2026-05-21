# 🐳 AWS Deployment with Docker - Easiest Method

Deploy bot to AWS using Docker (even simpler than manual setup).

---

## Why Docker on AWS?

✅ All dependencies included  
✅ No compilation issues  
✅ One command to deploy  
✅ Auto-restart if crashes  
✅ Easy to scale  

---

## Step 1: Create Dockerfile

Save in your repo root:

```dockerfile
# Dockerfile
FROM python:3.10-slim

# Install SIP dependencies
RUN apt-get update && apt-get install -y \
    libpjproject2.x \
    libpjproject2-dev \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Expose SIP port
EXPOSE 5060/udp
EXPOSE 5060/tcp

# Start bot
CMD ["python", "main.py"]
```

---

## Step 2: Create EC2 Instance (Same as Before)

```
AWS Console → EC2 → Launch Instances
- Ubuntu 22.04
- t2.micro
- Security group: Allow 5060 (TCP/UDP)
```

---

## Step 3: Install Docker on AWS

```bash
# SSH into instance
ssh -i key.pem ubuntu@your-aws-ip

# Install Docker
sudo apt-get update
sudo apt-get install -y docker.io

# Add ubuntu user to docker group
sudo usermod -aG docker ubuntu
newgrp docker

# Verify Docker
docker --version
```

---

## Step 4: Deploy Bot with Docker

### Option A: Build Locally, Push to AWS

```bash
# On your LOCAL machine

# 1. Build Docker image
docker build -t voice-bot:latest .

# 2. Tag for AWS
docker tag voice-bot:latest your-account-id.dkr.ecr.us-east-1.amazonaws.com/voice-bot:latest

# 3. Login to AWS ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin your-account-id.dkr.ecr.us-east-1.amazonaws.com

# 4. Push to AWS
docker push your-account-id.dkr.ecr.us-east-1.amazonaws.com/voice-bot:latest

# 5. SSH to AWS and pull
ssh -i key.pem ubuntu@your-aws-ip
docker pull your-account-id.dkr.ecr.us-east-1.amazonaws.com/voice-bot:latest
```

### Option B: Build Directly on AWS (Easier)

```bash
# SSH to AWS
ssh -i key.pem ubuntu@your-aws-ip

# Clone your repo
git clone https://github.com/your-repo.git
cd Agent-Stream-Voice-Agent

# Build Docker image on AWS
docker build -t voice-bot:latest .
```

---

## Step 5: Run Bot in Docker Container

```bash
# Create .env file on AWS
cat > .env << 'EOF'
USE_SIP_TRUNK=true
SIP_PUBLIC_IP=your-aws-ip
SIP_SERVER_PORT=5060
OPENAI_API_KEY=your-key
COMPANY_NAME=Your Company
SALES_BOT_NAME=Sarah
EOF

# Run Docker container
docker run -d \
  --name voice-bot \
  --env-file .env \
  -p 5060:5060/tcp \
  -p 5060:5060/udp \
  --restart always \
  voice-bot:latest

# Check if running
docker ps
```

---

## Step 6: Monitor Bot in Docker

```bash
# View logs
docker logs -f voice-bot

# Check container status
docker ps

# Stop container
docker stop voice-bot

# Start container
docker start voice-bot

# Remove container
docker rm voice-bot
```

---

## Troubleshooting Docker

### Container won't start
```bash
# View detailed logs
docker logs voice-bot

# Check ports
docker port voice-bot

# Inspect container
docker inspect voice-bot
```

### Rebuild image
```bash
docker build --no-cache -t voice-bot:latest .
```

### Remove old images
```bash
docker rmi voice-bot:old-version
```

---

## Docker Commands Reference

| Task | Command |
|------|---------|
| Build | `docker build -t voice-bot .` |
| Run | `docker run -d --env-file .env -p 5060:5060 voice-bot` |
| Logs | `docker logs -f voice-bot` |
| List | `docker ps` |
| Stop | `docker stop voice-bot` |
| Start | `docker start voice-bot` |
| Restart | `docker restart voice-bot` |
| Remove | `docker rm voice-bot` |

---

## Docker Compose (Advanced)

For even easier management, use Docker Compose:

```yaml
# docker-compose.yml
version: '3.8'

services:
  voice-bot:
    build: .
    container_name: voice-bot
    env_file: .env
    ports:
      - "5060:5060/tcp"
      - "5060:5060/udp"
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

Run with:
```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
```

---

## Cost

- EC2: $0-10/month
- Docker: Free
- Storage: ~100MB
- **Total**: ~$5-10/month

---

## Deployment Comparison

| Method | Time | Complexity | Recommended |
|--------|------|-----------|------------|
| **Manual** | 15 min | Medium | If familiar with Linux |
| **Docker** | 10 min | Low | **Recommended** ⭐ |
| **Docker Compose** | 8 min | Very Low | **Best** ⭐⭐⭐ |

---

## Which to Choose?

**👉 Use Docker Compose** for easiest, most professional setup!

Just run:
```bash
docker-compose up -d
```

And you're done! 🚀

---

## Next

1. **Git push** this repo with Dockerfile
2. **Deploy to AWS**
3. **Configure Exotel**
4. **Start receiving calls!**

See: `AWS_DEPLOYMENT.md` for full manual setup  
Or use: `docker-compose up -d` for Docker setup

---

**Choose Docker. It's easier!** 🐳
