# ⚡ AWS Deployment - Quick Summary

Deploy your bot to AWS in 15 minutes!

---

## 5 Simple Steps:

### 1️⃣ Create EC2 Instance (5 min)
```
AWS Console → EC2 → Launch Instances
- Ubuntu 22.04 LTS
- t2.micro (free tier)
- Security Group: Allow ports 22, 5060 (TCP/UDP)
- Download key.pem
```

### 2️⃣ SSH into Instance (1 min)
```bash
ssh -i key.pem ubuntu@your-aws-ip
```

### 3️⃣ Install & Deploy (5 min)
```bash
sudo apt-get update
sudo apt-get install -y libpjproject2-dev python3-pip git

cd /opt
git clone https://github.com/your-repo.git
cd Agent-Stream-Voice-Agent

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4️⃣ Configure .env (2 min)
```bash
nano .env
```

Paste:
```
USE_SIP_TRUNK=true
SIP_PUBLIC_IP=your-aws-public-ip
SIP_SERVER_PORT=5060
OPENAI_API_KEY=your-key
COMPANY_NAME=Your Company
SALES_BOT_NAME=Sarah
```

Save: `Ctrl+X` → `Y` → `Enter`

### 5️⃣ Start Bot (2 min)
```bash
# Run in background
nohup python main.py > bot.log 2>&1 &

# Check it's running
ps aux | grep python
netstat -an | grep 5060
```

---

## Configure in Exotel

1. **Dashboard** → **Manage** → **SIP Trunks**
2. **Add Trunk**:
   - Server: `sip://your-aws-ip:5060`
   - Authentication: IP-based
3. **Assign to Number**
4. **Test Call** ✅

---

## That's It! 🎉

Bot is now:
- ✅ Running on AWS
- ✅ Listening on port 5060
- ✅ Ready to receive Exotel calls

**Done in 15 minutes!**

---

## Getting Your AWS IP:

1. AWS Console → EC2 → Instances
2. Click your instance
3. Copy "Public IPv4 address"
4. Use in Exotel SIP trunk config

Example: `sip://54.123.45.67:5060`

---

## Monitor Bot:

```bash
# View logs
tail -f bot.log

# Check if running
ps aux | grep python

# Check SIP port
netstat -an | grep 5060
```

---

## Full Guide:

For detailed steps, security groups, systemd setup, troubleshooting:

👉 See: `AWS_DEPLOYMENT.md`

---

## Cost:

- **First year**: $0 (free tier)
- **After that**: ~$10/month (t2.micro)

---

**Ready?** Go to AWS Console and create instance! 🚀
