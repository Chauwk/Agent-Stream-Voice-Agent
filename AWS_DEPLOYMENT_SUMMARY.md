# 🚀 AWS Deployment - Complete Summary

Three ways to deploy your bot to AWS. Pick one!

---

## 🏃 Fastest Way: Docker Compose (Recommended)

**Time**: 10 minutes  
**Files included**: ✅ Dockerfile, docker-compose.yml

### Steps:

1. **Create AWS EC2 (Ubuntu 22.04)**
   - Instance: t2.micro (free)
   - Security group: Allow port 5060 (TCP/UDP)
   - Get public IP

2. **SSH into AWS**
   ```bash
   ssh -i key.pem ubuntu@your-aws-ip
   ```

3. **Install Docker**
   ```bash
   sudo apt-get update
   sudo apt-get install -y docker.io
   sudo usermod -aG docker ubuntu
   newgrp docker
   ```

4. **Clone and Deploy**
   ```bash
   git clone https://github.com/your-repo.git
   cd Agent-Stream-Voice-Agent
   docker-compose up -d
   ```

5. **Check Status**
   ```bash
   docker ps
   docker logs -f voice-bot
   ```

**Done!** Bot running on AWS. ✅

---

## 📝 Manual Setup (Most Control)

**Time**: 15 minutes  
**Recommended if**: You want to understand the setup

### Steps:
See: `AWS_DEPLOYMENT.md`

Key commands:
```bash
# Install dependencies
sudo apt-get install -y libpjproject2-dev python3-pip

# Clone and setup
git clone <repo>
cd Agent-Stream-Voice-Agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run in background
nohup python main.py > bot.log 2>&1 &
```

---

## 🐳 Docker Direct (Flexible)

**Time**: 12 minutes  
**Recommended if**: You know Docker

### Commands:
```bash
# Build
docker build -t voice-bot .

# Run
docker run -d \
  --env-file .env \
  -p 5060:5060/tcp \
  -p 5060:5060/udp \
  voice-bot:latest

# Monitor
docker logs -f voice-bot
```

See: `DOCKER_AWS_DEPLOYMENT.md`

---

## 📋 Pre-Deployment Checklist

- [ ] AWS account created
- [ ] EC2 instance launched (Ubuntu 22.04)
- [ ] Security group allows port 5060
- [ ] SSH key downloaded and saved safely
- [ ] OpenAI API key ready
- [ ] Bot repo cloned with Dockerfile
- [ ] .env file prepared

---

## 🔧 Pre-Deployment Configuration

### 1. Prepare .env

```bash
# Get AWS public IP
# AWS Console → EC2 → Instances → Copy Public IPv4

# Create .env
USE_SIP_TRUNK=true
SIP_PUBLIC_IP=your-aws-public-ip  # CHANGE THIS
SIP_SERVER_PORT=5060
OPENAI_API_KEY=your-key           # CHANGE THIS
COMPANY_NAME=Your Company         # CHANGE THIS
SALES_BOT_NAME=Sarah
```

### 2. Prepare Exotel Config

Get ready to configure:
- SIP Trunk Server: `sip://your-aws-ip:5060`
- Authentication: IP-based

---

## 🎯 Deployment Path (Choose One)

### Path 1: Docker Compose ⭐ RECOMMENDED
```
EC2 Created
    ↓
Docker Installed
    ↓
docker-compose up -d
    ↓
✅ Bot Running
```

### Path 2: Manual Setup
```
EC2 Created
    ↓
Dependencies Installed
    ↓
Bot Cloned & Configured
    ↓
nohup python main.py &
    ↓
✅ Bot Running
```

### Path 3: Docker Build
```
EC2 Created
    ↓
Docker Installed
    ↓
docker build && docker run
    ↓
✅ Bot Running
```

---

## ⚡ Quick Reference

| Task | Docker Compose | Manual | Docker |
|------|---|---|---|
| **Build** | `docker-compose build` | Manual install | `docker build` |
| **Run** | `docker-compose up -d` | `nohup python main.py &` | `docker run -d` |
| **Logs** | `docker-compose logs -f` | `tail -f bot.log` | `docker logs -f` |
| **Stop** | `docker-compose down` | `pkill -f python` | `docker stop` |
| **Restart** | `docker-compose restart` | `pkill; nohup...` | `docker restart` |

---

## 📊 Cost Breakdown

| Component | Cost |
|-----------|------|
| EC2 t2.micro | $0/mo (1st year) |
| Data transfer | ~$1-5/mo |
| **Total** | **$0-5/mo** (first year) |

---

## 🔗 Next Steps After Deployment

### 1. Get AWS Public IP
```
AWS Console → EC2 → Instances
Copy: Public IPv4 address
```

### 2. Configure Exotel
```
Exotel Dashboard → Manage → SIP Trunks
Add Trunk:
  - Server: sip://your-aws-ip:5060
  - Auth: IP-based
Assign to Phone Number
```

### 3. Test Call
```
Call your Exotel number
Bot should answer ✅
```

### 4. Monitor
```
# If Docker
docker logs -f voice-bot

# If Manual
tail -f bot.log
```

---

## 📁 Files Included

| File | Purpose |
|------|---------|
| `Dockerfile` | Docker image definition |
| `docker-compose.yml` | Docker orchestration |
| `AWS_DEPLOYMENT.md` | Full manual deployment guide |
| `DOCKER_AWS_DEPLOYMENT.md` | Docker deployment guide |
| `AWS_QUICK_START.md` | 5-step quick guide |

---

## 🆘 Troubleshooting

### Bot won't start
```bash
# Check logs
docker logs voice-bot

# Check port
sudo netstat -an | grep 5060
```

### Can't SSH
```bash
# Security group should allow port 22
# Check AWS Console → Security Groups
```

### Exotel not routing calls
```bash
# 1. Check AWS IP is correct
# 2. Check SIP trunk configured
# 3. Contact Exotel support
```

### Out of memory
```bash
# Use larger instance: t2.small
# Or optimize bot code
```

---

## 🎓 Learning Path

**Complete Beginner:**
1. Use `docker-compose up -d`
2. Follow `AWS_QUICK_START.md`
3. Done!

**Want to Learn:**
1. Follow `AWS_DEPLOYMENT.md`
2. Manual setup
3. Understand each step

**DevOps/Docker Expert:**
1. Use `DOCKER_AWS_DEPLOYMENT.md`
2. Customize docker-compose.yml
3. Advanced monitoring

---

## ✅ Your Next Action

**Right Now:**

1. Go to AWS Console
2. Create EC2 instance (Ubuntu 22.04, t2.micro)
3. Download SSH key
4. Come back here

**Then:**

Choose your deployment path:
- 🐳 **Docker Compose** (easiest) → Follow steps 1-5 above
- 📝 **Manual** (learn) → Read AWS_DEPLOYMENT.md
- 🐳 **Docker** (flexible) → Read DOCKER_AWS_DEPLOYMENT.md

---

## 📞 Support

**AWS Issues:**
- AWS Docs: https://docs.aws.amazon.com/ec2/
- AWS Support: Console.aws.amazon.com/support

**Docker Issues:**
- Docker Docs: https://docs.docker.com
- Docker Hub: https://hub.docker.com

**Bot Issues:**
- Check logs
- Verify .env configuration
- Contact Exotel support

---

## 🎉 Success Criteria

You're done when:
- ✅ EC2 instance running on AWS
- ✅ Bot process listening on port 5060
- ✅ Exotel SIP trunk configured
- ✅ Test call received by bot
- ✅ Bot answers and converses

---

**Ready to deploy?** 🚀

Start with EC2 creation, then use Docker Compose for fastest setup!
