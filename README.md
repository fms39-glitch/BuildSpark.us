# ⚡ BuildSpark: The Ultimate AI Agency In A Box

*What if you could spin up a fully-autonomous AI phone agent and lead generation machine in less than 5 minutes—without writing a single line of Twilio code, and without paying a dime in subscription fees?*

Welcome to **BuildSpark**. We've eliminated the friction of old-school telecom APIs and built the ultimate, streamlined stack for modern AI development agencies.

### 🧨 The Problem
Traditional AI voice agents are a nightmare to build. You need Twilio for the phone number, ngrok to tunnel through your local machine, complex state management, and expensive monthly subscriptions just to test your ideas. It's too slow, too fragile, and too expensive.

### ⚡ The BuildSpark Solution
We ripped out the old stack and replaced it with **Vapi** and **Google Gemini 1.5 Flash**. 
- **No Twilio.** 
- **No ngrok.** 
- **100% Free to start.**

BuildSpark is a complete Flask-based agency backend that seamlessly receives webhook data from your Vapi AI agents, stores leads in a sleek SQLite database, and automatically triggers beautifully formatted email notifications the second a call ends.

---

## 💰 The Stack (Your Costs: $0)

| Tech | Cost | Why We Use It |
|------|------|---------------|
| **Flask (Python)** | Free | Lightweight, insanely fast backend API. |
| **Vapi.ai** | Free Trial | The industry standard for AI voice. Zero local tunneling required. |
| **Google Gemini API** | Free Forever | 1M tokens/day of free, lightning-fast LLM reasoning. |
| **SQLite + HTML/CSS** | Free | Zero-setup database and beautiful admin dashboards out of the box. |

---

## 🛠️ The Architecture

```text
📞 Customer calls your Vapi Number (or uses the Web Chat)
         ↓
🧠 Vapi ping-pongs with Gemini to handle the natural conversation
         ↓
✅ Call Ends
         ↓
🪝 Vapi hits your Flask Webhook (`/vapi/end`) with the full transcript
         ↓
💾 Flask extracts the lead (Name, Email, Budget, Idea) & saves to DB
         ↓
📧 Gmail App Passwords instantly emails you the new lead and sends a receipt to the client.
```

---

## 🚀 Setup Guide: From Zero to Live in 3 Minutes

### Step 1: Clone & Install
```bash
# Create and activate your virtual environment
python -m venv env
.\env\Scripts\Activate.ps1   # Windows
# source env/bin/activate    # Mac/Linux

# Install the goods
pip install -r requirements.txt
```

### Step 2: Configure Your `.env`
Create a `.env` file in the root directory (copy from `.env.example` if you have it) and add these 3 things:
```env
# 1. Your Google Gemini API Key (Free from aistudio.google.com)
GEMINI_API_KEY=your_gemini_key_here

# 2. Your Gmail credentials for sending out automated lead emails
MAIL_USERNAME=your.agency@gmail.com
MAIL_PASSWORD=your_16_char_app_password

# 3. Where you want the system to alert you when a lead comes in
NOTIFY_EMAIL=your.personal@email.com
```
*(Need help getting a Gmail App Password? Go to [Google Account Security](https://myaccount.google.com/security) -> 2-Step Verification -> App Passwords).*

### Step 3: Run the Engine
```bash
python app.py
```
*Boom. Your backend is live on `localhost:5000`.*

### Step 4: Connect Vapi
1. Go to **[Vapi.ai](https://vapi.ai)** and create your free assistant.
2. In your Vapi Assistant settings, scroll down to **Server URL**.
3. *Note: Since we use Vapi, you just need to expose your Flask app to the internet. If developing locally, you can use a quick local tunnel tool, or deploy Flask for free on Render/Railway!*
4. Point the Server URL to: `https://your-domain.com/vapi/chat`
5. Vapi handles the voice. Flask handles the business logic.

---

## 📊 The Dashboards

We didn't just build an API; we built a business OS.
- 🌐 **The Website:** `http://localhost:5000/` – Your beautiful agency front-end.
- 📋 **The Lead CRM:** `http://localhost:5000/admin/leads` – Watch the money roll in.
- 📞 **The Call Logs:** `http://localhost:5000/admin/calls` – Read full transcripts of every AI interaction.

---

## 🚀 The Value Proposition

With this stack, you can spin up voice agents for real estate, e-commerce, and SaaS companies in hours instead of weeks. The margins are incredible, the infrastructure is zero-maintenance, and the AI is completely customizable. 

We are making this available completely free to empower the next generation of AI builders. If you find this valuable, dropping a GitHub Star ⭐ is the highest compliment.

---
*Built with ⚡ by Faizan Shaikh | BuildSpark | Newark, NJ*