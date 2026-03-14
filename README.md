# ⚡ BuildSpark — Setup Guide (100% Free Stack)

## What You Need (All Free)

| Service | Cost | What it does |
|---------|------|--------------|
| Gmail App Password | Free | Sends lead notification emails |
| Twilio | Free trial (~$15 credit) | Gives you a real phone number |
| Google Gemini API | Free forever | AI brain for phone conversations |
| ngrok | Free tier | Tunnels localhost for Twilio |

---

## File Structure

```
COMPANY/
├── app.py                ← Flask app: website routes + Twilio webhooks + email
├── voice_agent.py        ← AI brain: Gemini conversation + lead extraction
├── templates/
│   └── index.html        ← Full website frontend
├── .env                  ← Your secrets (create from .env.example)
├── .env.example          ← Template with instructions for every key
├── .gitignore            ← Keeps .env out of Git
├── requirements.txt      ← Python dependencies
├── Procfile              ← For future cloud deployment
└── README.md             ← This file
```

---

## How the AI Call Works

```
Someone dials your Twilio number
         ↓
Twilio hits your /voice webhook (via ngrok → localhost:5000)
         ↓
Flask returns TwiML: "Hey, I'm Spark..." (Amazon Polly voice)
         ↓
Caller speaks → Twilio transcribes speech → sends to /voice/respond
         ↓
Flask sends transcript to Gemini 1.5 Flash (free AI)
         ↓
Gemini replies naturally: answers FAQs, collects name/email/idea/budget
         ↓
Flask wraps reply in TwiML → Twilio speaks it to caller
         ↓  (loops until lead collected)
Gemini signals LEAD_COMPLETE with JSON data
         ↓
Lead saved to SQLite DB + email sent to Faizan + confirmation to caller
```

---

## Step 1 — Install Python dependencies

```bash
cd COMPANY

# Create virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# Install packages
pip install -r requirements.txt
```

---

## Step 2 — Create your .env file

```bash
cp .env.example .env
```

Then fill in each value using Steps 3–5 below.

---

## Step 3 — Gmail App Password (2 minutes)

1. Go to **https://myaccount.google.com/security**
2. Make sure **2-Step Verification** is ON
3. Go to **https://myaccount.google.com/apppasswords**
4. Create a new app password → name it "BuildSpark"
5. Copy the 16-character password
6. In your `.env`: set `MAIL_PASSWORD=` to that 16-char password

---

## Step 4 — Google Gemini API Key (30 seconds, free forever)

1. Go to **https://aistudio.google.com/app/apikey**
2. Sign in with any Google account
3. Click **"Create API key"**
4. Copy the key
5. In your `.env`: set `GEMINI_API_KEY=` to your key

**Free limits:** 15 requests/minute, 1 million tokens/day. More than enough.

---

## Step 5 — Twilio Free Trial (~5 minutes)

1. Sign up at **https://twilio.com** (free, no credit card for trial)
2. Verify your phone number during signup
3. Go to **https://console.twilio.com**
4. Copy your **Account SID** and **Auth Token** from the dashboard
5. Go to **Phone Numbers → Manage → Buy a Number**
   - Search for a US number with Voice capability
   - Click Buy (free with trial credit)
   - Note the number → paste into `.env` as `TWILIO_PHONE_NUMBER`
6. Paste SID and Token into `.env`

> ⚠️ **Twilio trial limitation:** With a free trial account, your Twilio number can only call/receive calls from **verified numbers**. To verify a number: Console → Phone Numbers → Verified Caller IDs. Upgrade to a paid account ($1/month) when going live.

---

## Step 6 — Install and run ngrok

ngrok creates a public HTTPS URL that tunnels to your local Flask app.
Twilio needs this to reach your machine.

**Install ngrok:**
- Mac: `brew install ngrok/ngrok/ngrok`
- Windows: Download from https://ngrok.com/download and add to PATH
- Or any OS: `pip install pyngrok` then use `pyngrok` below

**One-time setup (free account):**
1. Sign up at https://ngrok.com
2. Go to https://dashboard.ngrok.com/get-started/your-authtoken
3. Copy your token
4. Run: `ngrok config add-authtoken YOUR_TOKEN`

---

## Step 7 — Run Everything

You need **two terminal windows** open at once:

**Terminal 1 — Flask app:**
```bash
# Make sure your .venv is activated
python app.py
```
You should see:
```
╔══════════════════════════════════════════════════════╗
║           BuildSpark is Running! ⚡                  ║
║  Website:      http://localhost:5000                 ║
║  Leads DB:     http://localhost:5000/admin/leads     ║
║  Call Logs:    http://localhost:5000/admin/calls     ║
╚══════════════════════════════════════════════════════╝
```

**Terminal 2 — ngrok tunnel:**
```bash
ngrok http 5000
```
You'll see a URL like: `https://abc123.ngrok-free.app`

---

## Step 8 — Connect Twilio to ngrok

1. Go to **https://console.twilio.com/us1/develop/phone-numbers/manage/active**
2. Click your phone number
3. Scroll to **Voice Configuration**
4. Under **"A call comes in"** set:
   - Webhook URL: `https://abc123.ngrok-free.app/voice`
   - HTTP Method: **POST**
5. Click **Save configuration**

> ⚠️ The ngrok URL **changes every session** on the free plan.
> After each restart of ngrok, update the Twilio webhook URL.
> Tip: Copy the new URL from the ngrok terminal output each time.

---

## Step 9 — Test It!

1. ✅ Flask running (`python app.py`)
2. ✅ ngrok running (`ngrok http 5000`)
3. ✅ Twilio webhook pointing to your ngrok URL + `/voice`
4. 📞 **Call your Twilio number from a verified phone**
5. Spark will answer and have a conversation with you

**After the call check:**
- http://localhost:5000/admin/leads → lead should appear with 📞 badge
- http://localhost:5000/admin/calls → call transcript logged
- Your Gmail inbox → notification email from BuildSpark

---

## Admin Pages

| URL | What you see |
|-----|-------------|
| http://localhost:5000 | Main website |
| http://localhost:5000/admin/leads | All leads (web form + phone calls) |
| http://localhost:5000/admin/calls | Call logs with transcripts |

---

## Customising Spark (the AI)

Edit `voice_agent.py` → `SYSTEM_PROMPT` to change:
- Spark's personality and tone
- Pricing information
- Available discovery call times
- What information to collect

Change the voice in `app.py` by finding `voice="Polly.Joanna"` and replacing with:
- `Polly.Matthew` (US male)
- `Polly.Amy` (UK female)
- `Polly.Brian` (UK male)
- Full list: https://www.twilio.com/docs/voice/twiml/say/text-speech

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Call goes to voicemail | Check Flask is running + ngrok is running + Twilio webhook is correct |
| ngrok URL changed | Restart ngrok, copy new URL, update Twilio webhook |
| "Gemini API error" in logs | Check GEMINI_API_KEY in .env |
| Emails not sending | Check MAIL_PASSWORD is a Gmail App Password (not regular password) |
| Twilio trial error | Verify your caller phone number in Twilio console |
| Call connects but no response | Check Flask logs for errors in terminal |

---

## Going Live (Future)

When ready to deploy publicly:
1. Deploy to **Render.com** (free tier) or **Railway.app** (~$5/mo)
2. Set your `.env` variables in the platform's dashboard
3. Update Twilio webhook to your permanent production URL
4. No more ngrok needed — Twilio talks directly to the server
5. Upgrade Twilio trial to paid ($1/month base) to remove restrictions

---

Built with ⚡ by BuildSpark | Newark, NJ | buildspark.agency@gmail.com