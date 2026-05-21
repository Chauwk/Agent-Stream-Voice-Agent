# 🚀 AWS Deployment - Visual Flowchart

Complete deployment journey from start to finish.

---

## Deployment Decision Tree

```
                START
                  │
        ┌─────────┴─────────┐
        │                   │
    Know Docker?        Prefer Learning?
        │                   │
       YES                 NO
        │                   │
        ▼                   ▼
   ┌─────────┐         ┌──────────┐
   │ Docker  │         │  Manual  │
   │Compose  │         │  Setup   │
   └────┬────┘         └────┬─────┘
        │                   │
        ▼                   ▼
   [Fast Setup]        [Learn Setup]
   10 minutes          15 minutes
```

---

## Full Deployment Flow

```
┌─────────────────────────────────────────────────────────────┐
│                   DEPLOYMENT JOURNEY                        │
└─────────────────────────────────────────────────────────────┘

STEP 1: AWS Setup (5 minutes)
┌─────────────────────┐
│ • Create AWS Account│
│ • Launch EC2        │
│ • Ubuntu 22.04      │
│ • t2.micro          │
│ • Port 5060 open    │
│ • Get SSH key       │
│ • Get Public IP     │
└──────────┬──────────┘
           │
           ▼
STEP 2: SSH Connection (1 minute)
┌─────────────────────┐
│ ssh -i key.pem      │
│ ubuntu@AWS_IP       │
└──────────┬──────────┘
           │
           ├─────────────────────┐
           │                     │
           ▼                     ▼
STEP 3a:              STEP 3b:
Docker Setup          Manual Setup
(10 min)              (15 min)
┌──────────────┐      ┌──────────────────┐
│• apt-get     │      │• apt-get update  │
│  install     │      │• install deps    │
│  docker.io   │      │• python venv     │
│• chmod ubuntu│      │• pip install     │
└──────┬───────┘      └────────┬─────────┘
       │                       │
       ▼                       ▼
git clone repo          git clone repo
docker-compose          nano .env
up -d                   python main.py
       │                       │
       └───────────┬───────────┘
                   │
                   ▼
STEP 4: Configuration (5 min)
┌─────────────────────┐
│ Exotel Dashboard    │
│ • Create SIP Trunk  │
│ • Add AWS IP        │
│ • Assign to Number  │
└──────────┬──────────┘
           │
           ▼
STEP 5: Testing (3 min)
┌─────────────────────┐
│ • Call Number       │
│ • Bot Answers ✅    │
│ • Check Logs        │
└──────────┬──────────┘
           │
           ▼
      SUCCESS! 🎉
   Bot is Live on AWS
```

---

## Docker Compose Path (Easiest)

```
┌────────────────────────────┐
│ AWS EC2 Instance Created   │ (Ubuntu 22.04, t2.micro)
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Docker Installed           │
│ $ sudo apt-get install     │
│   docker.io                │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Repository Cloned          │
│ $ git clone repo           │
│ $ cd Agent-Stream          │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ docker-compose.yml Ready   │
│ (Included in repo)         │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Single Command Deploys     │
│ $ docker-compose up -d     │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Bot Running!               │
│ ✅ Listening on 5060       │
│ ✅ Auto-restart enabled    │
│ ✅ Logs available          │
└────────────┬───────────────┘
             │
             ▼
       🎉 DONE!
```

---

## Architecture After Deployment

```
                    CUSTOMER
                       │
                    📞 Call
                       │
                       ▼
        ┌───────────────────────────────┐
        │    Exotel Infrastructure      │
        │  (Phone Number Routing)       │
        └───────────┬───────────────────┘
                    │
              Routes call to
                    │
                    ▼
        ┌───────────────────────────────┐
        │     AWS EC2 Instance          │
        │  [Public IP: 54.123.45.67]    │
        └───────────┬───────────────────┘
                    │
                    ▼
        ┌───────────────────────────────┐
        │    SIP Port 5060              │
        │  (Listening for calls)        │
        └───────────┬───────────────────┘
                    │
                    ▼
        ┌───────────────────────────────┐
        │  Docker Container             │
        │  voice-bot:latest             │
        └───────────┬───────────────────┘
                    │
                    ▼
        ┌───────────────────────────────┐
        │    Python Bot Process         │
        │  (main.py)                    │
        └───────────┬───────────────────┘
                    │
                    ▼
        ┌───────────────────────────────┐
        │  OpenAI Realtime API          │
        │  (Speech Understanding)       │
        └───────────────────────────────┘
```

---

## Timeline

```
T+0min   - Start at AWS Console
T+5min   - EC2 instance running
T+6min   - SSH connected
T+7min   - Docker installed
T+8min   - Repository cloned
T+10min  - docker-compose up -d started
T+15min  - Bot fully running
T+16min  - Exotel SIP trunk configured
T+17min  - Test call initiated
T+20min  - Bot answering calls ✅

TOTAL: 20 minutes from start to live!
```

---

## Status Checks During Deployment

```
After EC2 Creation:
$ aws ec2 describe-instances
→ Should show: "running"

After SSH Connection:
$ docker --version
→ Should show: Docker version X.X.X

After docker-compose up:
$ docker ps
→ Should show: voice-bot container RUNNING

After Exotel Config:
$ docker logs -f voice-bot
→ Should show: "SIP Server initialized"

Test Call:
$ docker logs voice-bot | grep "SIP call"
→ Should show: "Incoming SIP call from..."
```

---

## Monitoring Dashboard

```
Real-Time Status:

Port Status:          ✅ 5060 (SIP)
                      ✅ 5000 (WebSocket)

Bot Status:           ✅ Running (Docker)
                      ✅ Auto-restart enabled

Connection Status:    ✅ Exotel trunk active
                      ✅ OpenAI connected

Recent Calls:         ✅ 0 (waiting)
                      ✅ Last call: 2 min ago
                      ✅ Avg duration: 5 min

Uptime:               ✅ 48 hours
Resource Usage:       ✅ CPU: 12%
                      ✅ Memory: 256MB
                      ✅ Disk: 500MB
```

---

## Quick Command Reference (During Deployment)

```
AWS SETUP
$ aws ec2 run-instances --image-id ami-xxx

SSH ACCESS
$ ssh -i key.pem ubuntu@54.123.45.67

DOCKER COMMANDS
$ docker-compose up -d           (Start)
$ docker ps                       (List)
$ docker logs -f voice-bot        (Monitor)
$ docker restart voice-bot        (Restart)
$ docker stop voice-bot           (Stop)

MONITORING
$ netstat -an | grep 5060         (Check SIP port)
$ ps aux | grep docker            (Check process)
$ df -h                           (Check disk)
$ free -h                         (Check memory)

MANUAL SETUP
$ git clone repo
$ python3 -m venv venv
$ source venv/bin/activate
$ pip install -r requirements.txt
$ nohup python main.py &
```

---

## Comparison: Deployment Methods

```
                  DOCKER-COMPOSE  |  MANUAL   |  DOCKER
─────────────────────────────────┼───────────┼─────────
Setup Time               10 min   |  15 min   | 12 min
Complexity              LOW       | MEDIUM    | LOW
Learning Value          Medium    | HIGH      | Medium
Production Ready        YES       | YES       | YES
Easy to Scale           YES       | NO        | YES
Auto-restart            YES       | MANUAL    | YES
Resource Usage          ~256MB    | ~200MB    | ~256MB
─────────────────────────────────┴───────────┴─────────

RECOMMENDED: Docker-Compose ⭐⭐⭐
```

---

## Success Indicators

```
✅ DEPLOYED SUCCESSFULLY WHEN:

1. EC2 Instance Status
   └─ Running (green check in AWS console)

2. SSH Connection
   └─ Can connect: ssh -i key.pem ubuntu@IP

3. Docker Status (if using Docker)
   └─ $ docker ps shows "voice-bot" RUNNING

4. SIP Port Listening
   └─ $ sudo netstat -an | grep 5060
      Shows: LISTENING 0.0.0.0:5060

5. Exotel Trunk Status
   └─ Exotel shows: "Trunk Active"

6. Test Call
   └─ Bot answers call automatically

7. Logs Show Activity
   └─ $ docker logs voice-bot (or tail bot.log)
      Shows: "SIP call received", "Bot responding"

All 7 checks green? 🎉 YOU'RE LIVE!
```

---

## Troubleshooting Flowchart

```
Bot not receiving calls?
    │
    ├─ Check: SIP port open?
    │  └─ $ netstat -an | grep 5060
    │     └─ If not listening → Bot crashed
    │        └─ Check logs: docker logs voice-bot
    │
    ├─ Check: Exotel trunk configured?
    │  └─ Exotel dashboard → SIP trunks
    │     └─ Should point to: sip://your-ip:5060
    │
    ├─ Check: Security group allows 5060?
    │  └─ AWS Console → Security Groups
    │     └─ Should have: 5060 TCP/UDP inbound
    │
    └─ Check: Public IP correct?
       └─ AWS Console → Instances
          └─ Copy Public IPv4 → Use in Exotel

Contact Exotel support if all above OK
```

---

**You've got this! Deploy with confidence!** 🚀
