# 🚀 Deploy Bot to AWS - Complete Guide

Step-by-step AWS deployment for your Voice Agent Bot with SIP Trunk.

---

## Step 1: Create EC2 Instance

### 1.1 Log in to AWS Console
- Go to: https://aws.amazon.com
- Sign in to your AWS account

### 1.2 Launch EC2 Instance

1. **Go to**: EC2 → Instances → Launch Instances
2. **Choose AMI**: 
   - Select: `Ubuntu Server 22.04 LTS`
   - Free tier eligible ✅

3. **Choose Instance Type**:
   - `t2.micro` (Free tier - 1 GB RAM)
   - Or `t2.small` (if you want more power - $0.02/hour)

4. **Configure Instance Details**:
   - VPC: Default
   - Subnet: Default
   - Auto-assign IP: Enable

5. **Add Storage**:
   - 20 GB (default is fine)

6. **Add Tags** (optional):
   - Name: `voice-agent-bot`

7. **Configure Security Group**:
   - **Create new**: Name it `voice-bot-sg`
   - **Add Rules**:
     ```
     Type              Protocol  Port   Source
     SSH               TCP       22     0.0.0.0/0  (Your IP for security)
     Custom UDP        UDP       5060   0.0.0.0/0  (SIP)
     Custom TCP        TCP       5060   0.0.0.0/0  (SIP)
     HTTP              TCP       80     0.0.0.0/0  (Optional)
     HTTPS             TCP       443    0.0.0.0/0  (Optional)
     ```

8. **Review & Launch**:
   - Click "Launch"
   - Choose key pair: Create new `voice-bot-key.pem`
   - Download and save securely

---

## Step 2: Connect to Instance

### 2.1 Get Public IP

1. Go to EC2 → Instances
2. Click your instance
3. Copy **Public IPv4 address** (e.g., `54.123.45.67`)

### 2.2 SSH into Instance

**Windows (using PuTTY or Windows Terminal):**
```bash
# If using OpenSSH (Windows 10+)
ssh -i "voice-bot-key.pem" ubuntu@54.123.45.67

# If using PuTTY:
# 1. Convert .pem to .ppk format (PuTTYgen)
# 2. Open PuTTY
# 3. Host: 54.123.45.67
# 4. Auth → Private key file: voice-bot-key.ppk
# 5. Connect
```

**Mac/Linux:**
```bash
chmod 400 voice-bot-key.pem
ssh -i voice-bot-key.pem ubuntu@54.123.45.67
```

---

## Step 3: Install Dependencies on AWS

Once connected via SSH:

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install required packages
sudo apt-get install -y \
    python3.10 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    nano

# Install SIP dependencies
sudo apt-get install -y \
    libpjproject2.x \
    libpjproject2-dev \
    portaudio19-dev

# Verify installations
python3 --version
pip3 --version
```

---

## Step 4: Clone and Setup Bot

```bash
# Navigate to /opt directory
cd /opt

# Clone your repository
git clone https://github.com/your-username/Agent-Stream-Voice-Agent.git
cd Agent-Stream-Voice-Agent

# Create Python virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install Python dependencies
pip install -r requirements.txt
```

---

## Step 5: Configure .env File

```bash
# Create .env file
nano .env
```

**Paste this configuration:**
```bash
# === CORE SETTINGS ===
USE_SIP_TRUNK=true
OPENAI_API_KEY=your-openai-api-key-here

# === SIP TRUNK (Inbound) ===
SIP_PUBLIC_IP=54.123.45.67  # Your AWS public IP
SIP_SERVER_PORT=5060
SIP_SERVER_HOST=0.0.0.0
INBOUND_SIP_ENABLED=true

# === SIP OUTBOUND (Optional) ===
OUTBOUND_SIP_ENABLED=true
SIP_USERNAME=your-sip-username
SIP_PASSWORD=your-sip-password
SIP_REALM=exotel.com
EXOTEL_OUTBOUND_PROXY=proxy.exotel.in:5060

# === REST API OUTBOUND (Optional) ===
EXOTEL_API_TOKEN=your-api-token
EXOTEL_ACCOUNT_SID=your-account-sid
EXOTEL_FROM_NUMBER=your-virtual-number

# === BOT PERSONALITY ===
COMPANY_NAME=Your Company
SALES_BOT_NAME=Sarah
SALES_REP_NAME=Sarah

# === AUDIO SETTINGS ===
SAMPLE_RATE=24000
AUDIO_CHUNK_SIZE=200

# === SERVER SETTINGS ===
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
LOG_LEVEL=INFO

# === PRODUCTION ===
PRODUCTION_MODE=true
```

**Save**: Press `Ctrl+X` → `Y` → `Enter`

---

## Step 6: Test Bot Locally on AWS

```bash
# Activate venv if not already
source venv/bin/activate

# Start bot
python main.py
```

**Expected output:**
```
📡 Mode: Direct SIP Trunking (cost-effective)
🔌 SIP Server: 0.0.0.0:5060
📥 Inbound vSIP: ✅ ENABLED
✅ Bot started and listening on port 5060
```

**Test from another terminal:**
```bash
# Check SIP port is listening
sudo netstat -an | grep 5060
# Should show: LISTENING on 0.0.0.0:5060
```

Press `Ctrl+C` to stop bot.

---

## Step 7: Configure Exotel SIP Trunk

### 7.1 In Exotel Dashboard

1. **Go to**: Manage → SIP Trunks
2. **Add New Trunk**:
   - **Name**: Voice Agent Bot
   - **Type**: Direct SIP
   - **Server Address**: `sip://54.123.45.67:5060`
   - **Authentication**: IP-based
   - **Trusted IPs**: (Ask Exotel support or leave as default)

3. **Assign to Phone Number**:
   - Go to: Numbers
   - Select your number
   - Incoming Calls → Route to: "Voice Agent Bot" trunk
   - Save

### 7.2 Whitelist AWS IP (if needed)

Contact Exotel support:
- Tell them: "Add AWS IP `54.123.45.67` to SIP trunk whitelist"

---

## Step 8: Run Bot in Background (Production)

```bash
# Go to bot directory
cd /opt/Agent-Stream-Voice-Agent

# Activate venv
source venv/bin/activate

# Create systemd service (auto-start on reboot)
sudo nano /etc/systemd/system/voice-bot.service
```

**Paste this:**
```ini
[Unit]
Description=Voice Agent Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/Agent-Stream-Voice-Agent
Environment="PATH=/opt/Agent-Stream-Voice-Agent/venv/bin"
ExecStart=/opt/Agent-Stream-Voice-Agent/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Save**: `Ctrl+X` → `Y` → `Enter`

**Enable service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable voice-bot
sudo systemctl start voice-bot

# Check status
sudo systemctl status voice-bot
```

**View logs:**
```bash
sudo journalctl -u voice-bot -f
```

---

## Step 9: Test Inbound Call

1. **From your phone**: Call your Exotel number
2. **Bot should answer** with greeting
3. **Speak to it**: Have a conversation
4. **Watch logs**:
   ```bash
   sudo journalctl -u voice-bot -f
   ```

---

## Step 10: Monitoring & Maintenance

### View Logs
```bash
# Real-time logs
sudo journalctl -u voice-bot -f

# Last 50 lines
sudo journalctl -u voice-bot -n 50

# Today's logs
sudo journalctl -u voice-bot --since today
```

### Restart Bot
```bash
sudo systemctl restart voice-bot
```

### Stop Bot
```bash
sudo systemctl stop voice-bot
```

### Check Bot is Running
```bash
ps aux | grep python
sudo netstat -an | grep 5060
```

### Monitor Resource Usage
```bash
# CPU and Memory
top
# Press 'q' to exit

# Disk usage
df -h

# Memory usage
free -h
```

---

## Troubleshooting

### Bot won't start
```bash
# Check logs
sudo journalctl -u voice-bot -n 100

# Check if port is in use
sudo lsof -i :5060

# Check SIP is running
sudo netstat -an | grep 5060
```

### Can't connect via SSH
```bash
# Check security group rules
# AWS Console → EC2 → Security Groups
# Should have SSH (port 22) open
```

### SIP calls not received
1. Check AWS security group allows port 5060
2. Check Exotel SIP trunk points to correct IP
3. Check IP whitelist with Exotel support

### Bot crashes
```bash
# Check logs for errors
sudo journalctl -u voice-bot -n 200

# Restart
sudo systemctl restart voice-bot

# Check if out of memory
free -h
```

---

## Cost Estimate

| Service | Cost/Month |
|---------|-----------|
| EC2 t2.micro | $0 (Free tier first year) |
| EC2 t2.small | ~$10 |
| Data transfer | ~$1-5 |
| **Total** | **$0-15/month** |

---

## Production Checklist

- [ ] EC2 instance created and running
- [ ] Security group configured with SIP ports
- [ ] Bot deployed on AWS
- [ ] SIP trunk configured in Exotel
- [ ] AWS IP whitelisted in Exotel (if needed)
- [ ] Test call successful
- [ ] Logs being captured
- [ ] Auto-restart enabled (systemd service)
- [ ] Monitoring setup
- [ ] Backup plan in place

---

## Next Steps

### Option 1: Setup Monitoring
```bash
# Install CloudWatch agent for AWS monitoring
# Or use third-party: Datadog, New Relic, etc.
```

### Option 2: Setup SSL (Optional)
```bash
# For HTTPS on port 80/443 if needed
sudo apt-get install certbot python3-certbot-nginx
```

### Option 3: Setup Auto-Scaling
```bash
# Use AWS Load Balancer for multiple instances
# Configure Auto Scaling Group
```

---

## Support

**AWS Issues?**
- AWS Docs: https://docs.aws.amazon.com/ec2/
- AWS Support: https://console.aws.amazon.com/support/

**Bot Issues?**
- Check logs: `sudo journalctl -u voice-bot -f`
- Check port: `sudo netstat -an | grep 5060`

**Exotel Issues?**
- Contact Exotel support with AWS IP: `54.123.45.67`
- Verify SIP trunk configuration

---

## Quick Reference

| Task | Command |
|------|---------|
| SSH into AWS | `ssh -i key.pem ubuntu@IP` |
| Start bot | `sudo systemctl start voice-bot` |
| Stop bot | `sudo systemctl stop voice-bot` |
| View logs | `sudo journalctl -u voice-bot -f` |
| Check SIP | `sudo netstat -an \| grep 5060` |
| Restart AWS | `sudo reboot` |

---

**You're now running the bot on AWS!** 🎉

Bot IP: `54.123.45.67` → Configure in Exotel → Start receiving calls!
