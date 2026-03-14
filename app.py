"""
BuildSpark — Flask App
══════════════════════════════════════════════════════════════
Routes:
  GET  /                     → Website
  POST /submit-contact       → Web form → save lead + send emails
  POST /vapi/chat            → Vapi sends caller message → Gemini replies
  POST /vapi/end             → Vapi call ended → save lead + send emails
  GET  /admin/leads          → All leads dashboard
  GET  /admin/calls          → All call logs

How Vapi connects:
  1. Someone calls your Vapi phone number
  2. Vapi sends each caller message to POST /vapi/chat
  3. Your Flask app calls Gemini → returns {"response": "..."}
  4. Vapi speaks that response to the caller
  5. When call ends, Vapi hits POST /vapi/end with full transcript
  6. Flask saves the lead + fires emails

No Twilio. No ngrok needed for Vapi testing (Vapi has a web tester).
══════════════════════════════════════════════════════════════
"""

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from datetime import datetime
import os, re, logging, sqlite3, json, requests as http_requests

load_dotenv()

from voice_agent import (
    get_ai_response,
    extract_lead_data,
    clean_for_speech,
    GREETING,
)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "buildspark-secret-2025")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("leads.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Brevo Email API ───────────────────────────────────────────────────────────
BREVO_API_KEY   = os.getenv("BREVO_API_KEY")
NOTIFY_EMAIL    = os.getenv("NOTIFY_EMAIL", "buildspark.agency@gmail.com")
FROM_EMAIL      = os.getenv("MAIL_USERNAME", "buildspark.agency@gmail.com")
FROM_NAME       = "Spark — BuildSpark"

# ── In-memory call sessions ───────────────────────────────────────────────────
# Key = Vapi call ID  |  Value = { history: [...], phone: str, attempts: int }
call_sessions: dict = {}

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = "buildspark_leads.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            email        TEXT    NOT NULL,
            phone        TEXT,
            project      TEXT,
            budget       TEXT,
            idea         TEXT,
            ip_address   TEXT,
            source       TEXT    DEFAULT 'web',
            scheduled    TEXT,
            status       TEXT    DEFAULT 'new',
            submitted_at TEXT    NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS call_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id      TEXT,
            caller_phone TEXT,
            lead_id      INTEGER,
            transcript   TEXT,
            started_at   TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialised ✓")

def save_lead(name, email, phone="", project="", budget="",
              idea="", ip="", source="web", scheduled=""):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        INSERT INTO leads
          (name, email, phone, project, budget, idea, ip_address, source, scheduled, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, email, phone, project, budget, idea, ip, source, scheduled,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    lead_id = c.lastrowid
    conn.close()
    return lead_id

def save_call_log(call_id, caller_phone, transcript, lead_id=None):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        INSERT INTO call_logs (call_id, caller_phone, transcript, lead_id, started_at)
        VALUES (?, ?, ?, ?, ?)
    """, (call_id, caller_phone, transcript, lead_id,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# ── Email helpers ─────────────────────────────────────────────────────────────
def valid_email(addr: str) -> bool:
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", addr))

def send_via_brevo(to: str, subject: str, html: str, reply_to: str = None):
    """Send email using Brevo API — 300 emails/day free, no domain needed."""
    if not BREVO_API_KEY:
        logger.error("BREVO_API_KEY not set — email not sent")
        return False
    payload = {
        "sender":      {"name": FROM_NAME, "email": FROM_EMAIL},
        "to":          [{"email": to}],
        "subject":     subject,
        "htmlContent": html,
    }
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    try:
        resp = http_requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key":      BREVO_API_KEY,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logger.info(f"Email sent via Brevo → {to}")
            return True
        else:
            logger.error(f"Brevo error {resp.status_code}: {resp.text}")
            return False
    except Exception as exc:
        logger.error(f"Brevo request failed: {exc}")
        return False


def send_notification_email(lead_id, name, email, phone,
                             project, budget, idea, source, scheduled, now):
    src_ico = "📞 Phone Call" if source == "call" else "🌐 Website Form"
    sched   = f"<div class='field'><div class='label'>Discovery Call</div><div class='value'>{scheduled}</div></div>" \
              if scheduled and scheduled != "Not scheduled" else ""
    html = f"""<!DOCTYPE html>
<html><head><style>
  body{{font-family:Arial,sans-serif;background:#080c14;margin:0;padding:0;}}
  .wrap{{max-width:600px;margin:0 auto;}}
  .header{{background:linear-gradient(135deg,#0ea5e9,#0369a1);padding:32px 36px;}}
  .header h1{{color:white;margin:0;font-size:22px;}}
  .header p{{color:rgba(255,255,255,.8);margin:6px 0 0;font-size:13px;}}
  .body{{background:#0f1720;padding:32px 36px;}}
  .field{{margin-bottom:22px;padding-left:14px;border-left:3px solid #0ea5e9;}}
  .label{{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#64748b;margin-bottom:5px;}}
  .value{{font-size:15px;color:#e2e8f0;font-weight:600;}}
  .idea-box{{background:#0a1628;border:1px solid #1e3a5f;padding:18px;margin-top:8px;border-radius:4px;}}
  .idea-box p{{color:#94a3b8;font-size:14px;line-height:1.7;margin:0;}}
  .badge{{display:inline-block;background:#0ea5e9;color:white;font-size:10px;
          letter-spacing:2px;text-transform:uppercase;padding:4px 10px;border-radius:2px;margin-bottom:24px;}}
  .src{{display:inline-block;background:rgba(14,165,233,.15);color:#0ea5e9;
        border:1px solid rgba(14,165,233,.3);font-size:11px;padding:3px 10px;
        border-radius:2px;margin-left:8px;}}
  .footer{{background:#050a10;padding:18px 36px;text-align:center;}}
  .footer p{{color:#334155;font-size:11px;margin:0;}}
  hr{{border:none;border-top:1px solid #1e3a5f;margin:24px 0;}}
  a{{color:#0ea5e9;}}
</style></head>
<body><div class="wrap">
  <div class="header">
    <h1>⚡ New Lead — BuildSpark</h1>
    <p>Someone just reached out via {src_ico}</p>
  </div>
  <div class="body">
    <span class="badge">Lead #{lead_id}</span>
    <span class="src">{src_ico}</span>
    <div style="height:20px;"></div>
    <div class="field"><div class="label">Name</div><div class="value">{name}</div></div>
    <div class="field"><div class="label">Email</div>
      <div class="value"><a href="mailto:{email}">{email}</a></div></div>
    <div class="field"><div class="label">Phone</div>
      <div class="value">{phone or 'Not provided'}</div></div>
    <div class="field"><div class="label">Project Type</div>
      <div class="value">{project or 'Not specified'}</div></div>
    <div class="field"><div class="label">Budget</div>
      <div class="value">{budget or 'Not specified'}</div></div>
    {sched}
    <div class="field"><div class="label">Idea / Call Summary</div>
      <div class="idea-box"><p>{idea}</p></div></div>
    <hr/>
    <p style="font-size:11px;color:#334155;">
      Submitted: {now} &nbsp;|&nbsp; Lead #{lead_id} saved in database
    </p>
  </div>
  <div class="footer">
    <p>BuildSpark &nbsp;|&nbsp; Newark, NJ &nbsp;|&nbsp; +1 (973) 554-3147</p>
  </div>
</div></body></html>"""
    send_via_brevo(
        to       = NOTIFY_EMAIL,
        subject  = f"⚡ New Lead #{lead_id} — {name} | {src_ico}",
        html     = html,
        reply_to = email if valid_email(email) else None,
    )


def send_confirmation_email(name, email, project, source="web", scheduled=""):
    if not valid_email(email):
        logger.warning(f"Skipping confirmation — invalid email: {email}")
        return
    via = "your call" if source == "call" else "your message"
    sched_line = ""
    if scheduled and scheduled != "Not scheduled":
        sched_line = f"""
    <div style="border-left:3px solid #f59e0b;padding:12px 16px;margin:16px 0;background:#0f1720;">
      <p style="margin:0;font-size:13px;color:#94a3b8;">
        Discovery call booked: <strong style="color:#f59e0b;">{scheduled}</strong>
      </p>
    </div>"""
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
     background:#080c14;padding:40px;color:#e2e8f0;">
  <h2 style="color:#0ea5e9;margin-bottom:10px;">Got it, {name}! ⚡</h2>
  <p style="color:#64748b;font-size:14px;line-height:1.8;">
    Thanks for {via}. Faizan will personally reach out within
    <strong style="color:#e2e8f0;">24 hours</strong>.
  </p>
  <div style="border-left:3px solid #0ea5e9;padding:12px 16px;
       margin:24px 0;background:#0f1720;">
    <p style="margin:0;font-size:13px;color:#94a3b8;">
      Project: <strong style="color:#e2e8f0;">{project or 'As described'}</strong>
    </p>
  </div>
  {sched_line}
  <p style="font-size:13px;color:#64748b;">
    Questions? Email us anytime:<br/>
    <strong style="color:#0ea5e9;">buildspark.agency@gmail.com</strong>
  </p>
  <hr style="border:none;border-top:1px solid #1e3a5f;margin:24px 0;"/>
  <p style="font-size:12px;color:#334155;">
    — Faizan Shaikh, Founder @ BuildSpark | Newark, NJ
  </p>
</div>"""
    send_via_brevo(
        to      = email,
        subject = "We got your idea! — BuildSpark ⚡",
        html    = html,
    )


# ══════════════════════════════════════════════════════════════
#  ROUTE — Website Chatbot (Spark FAQ bot)
# ══════════════════════════════════════════════════════════════

@app.route("/chat-widget", methods=["POST"])
def chat_widget():
    """
    Powers the embedded Spark chatbot on the website.
    Uses Gemini for smart FAQ answers.
    No phone call — just text chat in the browser.
    """
    data    = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()[:500]
    history = data.get("history", [])

    if not message:
        return jsonify({"reply": "Hey! Ask me anything about BuildSpark. 😊"})

    WIDGET_PROMPT = """You are Spark, the highly intelligent and friendly AI assistant embedded on the BuildSpark website.
BuildSpark is a premium app development agency in Newark, NJ, founded by Faizan Shaikh (Client & GenAI Lead) and Advik Yadav (Technical GenAI Expert).

Your goal is to act as the "brain" of BuildSpark. You know everything about how we work, what we build, and why we are better than traditional agencies.

CORE IDENTITY & VALUE PROPOSITION:
- We don't just write code; we "spark ideas into reality."
- We use AI-powered development (GenAI, vibe coding) to build products 3x faster than traditional agencies.
- We focus on beautiful, modern, Google-inspired design (glassmorphism, 3D tilts, aurora backgrounds).
- Clients get 100% ownership of their source code. There are no vendor lock-ins.

SERVICES & ESTIMATED PRICING:
1. Landing Pages & Business Websites: from $500 (1-2 weeks). Perfect for local businesses or portfolios.
2. E-Commerce Stores: $800 - $1,500 (2-3 weeks). Integrated with Stripe/Shopify headless.
3. Web Applications & Dashboards: $1,000 - $2,500 (2-4 weeks). SaaS tools, internal portals, custom CRM.
4. AI-Powered Tools: $1,500 - $3,000+ (3-5 weeks). Custom GPT wrappers, AI chatbots, automated workflows.
5. Browser Games: $800 - $2,000. Interactive, highly polished web gaming (e.g., Diamond Puzzle on suloku.com).
6. Booking Systems: $1,000 - $2,000. For salons, consultants, clinics.

OUR PROCESS (7 Steps):
1. Call/Message: Instant AI pickup 24/7.
2. Idea: Client shares their vision.
3. Validate: We check feasibility.
4. Plan: Wireframes & timeline.
5. Build: Fast MVP in 2-4 weeks.
6. Launch: Deployment & training.
7. Grow: Optional maintenance retainer.

CONTACT & SCHEDULING:
- Phone: +1 (973) 554-3147 (Our AI voice agent answers 24/7 instantly! No hold music.)
- Email: buildspark.agency@gmail.com
- Location: Newark, NJ (But we work remotely worldwide).
- Discovery Call: Free 30-minute consultation. Faizan replies to all leads within 24 hours.

CONVERSATION RULES:
- Be smart, engaged, and highly conversational. You are not a regular bot; you are Spark.
- Keep replies relatively concise (2-4 sentences usually), but if someone asks a complex question, give a smart, detailed answer.
- Highlight our speed (2-4 weeks) and AI-advantage when relevant.
- Use **bold** for key info (prices, timelines).
- If a user seems ready to start or is asking for a quote, strongly encourage them to fill out the contact form on this page or call +1 (973) 554-3147.
- Never make up information. If you don't know, say Faizan can answer that on a discovery call.
- Always try to end with a warm follow-up question to keep the chat going if they haven't explicitly said goodbye."""

    try:
        from voice_agent import _client, FALLBACK
        from google.genai import types
        if not _client:
            return jsonify({"reply": "I'm having a quick technical issue! Email us at buildspark.agency@gmail.com and we'll reply within 24 hours. ⚡"})

        gemini_history = []
        for msg in history[-8:]:  # last 8 messages for context
            role = "model" if msg.get("role") == "assistant" else "user"
            content = str(msg.get("content","")).strip()
            if content:
                gemini_history.append(types.Content(role=role, parts=[types.Part.from_text(content)]))

        full_chat = [
            types.Content(role="user", parts=[types.Part.from_text(f"[INSTRUCTIONS]\n{WIDGET_PROMPT}")]),
            types.Content(role="model", parts=[types.Part.from_text("Got it! I'm Spark, ready to help website visitors learn about BuildSpark.")]),
            *gemini_history,
            types.Content(role="user", parts=[types.Part.from_text(message)]),
        ]

        response = _client.models.generate_content(
            model='gemini-1.5-flash',
            contents=full_chat,
            config=types.GenerateContentConfig(
                max_output_tokens=200,
                temperature=0.75,
            )
        )
        reply    = response.text.strip()
        # Clean any markdown code blocks
        import re as _re
        reply = _re.sub(r'```.*?```', '', reply, flags=_re.DOTALL).strip()
        return jsonify({"reply": reply})

    except Exception as exc:
        logger.error(f"Chat widget error: {exc}")
        return jsonify({"reply": "Quick hiccup on my end! You can reach Faizan directly at **buildspark.agency@gmail.com** or call **+1 (973) 554-3147**. ⚡"})


# ══════════════════════════════════════════════════════════════
#  ROUTE — Website
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ══════════════════════════════════════════════════════════════
#  ROUTE — Web Contact Form
# ══════════════════════════════════════════════════════════════

@app.route("/submit-contact", methods=["POST"])
def submit_contact():
    data    = request.get_json(silent=True) or {}
    name    = str(data.get("name",    "")).strip()[:100]
    email   = str(data.get("email",   "")).strip()[:200]
    phone   = str(data.get("phone",   "")).strip()[:30]
    project = str(data.get("project", "")).strip()[:200]
    budget  = str(data.get("budget",  "")).strip()[:50]
    idea    = str(data.get("idea",    "")).strip()[:3000]
    ip      = request.headers.get("X-Forwarded-For",
                                   request.remote_addr).split(",")[0].strip()

    if not name or len(name) < 2:
        return jsonify({"status": "error", "message": "Please enter your name."}), 400
    if not valid_email(email):
        return jsonify({"status": "error", "message": "Please enter a valid email."}), 400
    if not idea:
        return jsonify({"status": "error", "message": "Please describe your idea."}), 400

    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    try:
        lead_id = save_lead(name, email, phone, project, budget, idea, ip, "web")
        logger.info(f"Web lead #{lead_id} saved — {name} | {email}")
    except Exception as exc:
        logger.error(f"DB save failed: {exc}")
        lead_id = "N/A"

    send_notification_email(lead_id, name, email, phone,
                             project, budget, idea, "web", "", now)
    send_confirmation_email(name, email, project, "web")

    return jsonify({
        "status":  "success",
        "message": "We got it! Faizan will reach out within 24 hours. "
                   "Check your email for confirmation.",
    })


# ══════════════════════════════════════════════════════════════
#  ROUTES — Vapi.ai Webhooks
# ══════════════════════════════════════════════════════════════

@app.route("/vapi/chat", methods=["POST"])
def vapi_chat():
    """
    Vapi calls this endpoint for every message in the conversation.

    Vapi sends JSON like:
    {
      "message": {
        "type": "assistant-request",
        "call": { "id": "call_abc123", "customer": { "number": "+1..." } },
        "messages": [
          { "role": "user", "content": "Hi I want a website" }
        ]
      }
    }

    We respond with:
    { "response": { "message": { "role": "assistant", "content": "..." } } }
    """
    body = request.get_json(silent=True) or {}
    msg  = body.get("message", {})

    call_info    = msg.get("call", {})
    call_id      = call_info.get("id", "unknown")
    caller_phone = call_info.get("customer", {}).get("number", "unknown")
    messages     = msg.get("messages", [])

    logger.info(f"Vapi chat | call_id={call_id} | from={caller_phone}")

    # Initialise session for new calls
    if call_id not in call_sessions:
        call_sessions[call_id] = {
            "history":  [],
            "phone":    caller_phone,
            "attempts": 0,
        }

    session = call_sessions[call_id]
    session["attempts"] += 1

    # Safety limit — end after 25 exchanges
    if session["attempts"] > 25:
        return jsonify({
            "response": {
                "message": {
                    "role":    "assistant",
                    "content": "It was wonderful speaking with you! "
                               "Faizan will be in touch soon. Have a great day!",
                }
            }
        })

    # Get the latest user message from Vapi's messages array
    user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_text = m.get("content", "").strip()
            break

    if not user_text:
        user_text = "[no input detected]"

    logger.info(f"Caller said: '{user_text}'")

    # Get Gemini reply
    ai_reply = get_ai_response(session["history"], user_text)

    # Check if AI has all lead info
    lead_data = extract_lead_data(ai_reply)
    speech    = clean_for_speech(ai_reply)

    if lead_data:
        _save_call_lead(call_id, caller_phone, session, lead_data)

    logger.info(f"Spark replies: '{speech[:80]}...'")

    return jsonify({
        "response": {
            "message": {
                "role":    "assistant",
                "content": speech,
            }
        }
    })


@app.route("/vapi/end", methods=["POST"])
def vapi_end():
    """
    Vapi calls this when the call ends.
    Contains the full transcript. We save everything here as a backup
    in case /vapi/chat's lead detection missed anything.
    """
    body         = request.get_json(silent=True) or {}
    msg          = body.get("message", {})
    call_info    = msg.get("call", {})
    call_id      = call_info.get("id", "unknown")
    caller_phone = call_info.get("customer", {}).get("number", "unknown")

    # Build transcript from messages
    messages   = msg.get("messages", [])
    transcript = "\n".join(
        f"{m.get('role','?').upper()}: {m.get('content','')}"
        for m in messages
    )

    logger.info(f"Call ended | call_id={call_id} | {len(messages)} messages")

    # Save call log regardless
    save_call_log(call_id, caller_phone, transcript)

    # Clean up session
    if call_id in call_sessions:
        del call_sessions[call_id]

    return jsonify({"status": "ok"})


@app.route("/vapi/greeting", methods=["GET", "POST"])
def vapi_greeting():
    """
    Optional: Vapi can hit this to get the first greeting message.
    Or just set the greeting directly in the Vapi dashboard.
    """
    return jsonify({
        "response": {
            "message": {
                "role":    "assistant",
                "content": GREETING,
            }
        }
    })


def _save_call_lead(call_id, caller_phone, session, lead_data):
    """Internal helper: save lead from a completed AI call."""
    now       = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    name      = lead_data.get("name",      "Phone Caller")
    email     = lead_data.get("email",     "")
    idea      = lead_data.get("idea",      "")
    budget    = lead_data.get("budget",    "")
    scheduled = lead_data.get("scheduled", "Not scheduled")
    project   = idea[:100] if idea else ""

    # Build transcript from history
    transcript = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in session["history"]
    )

    try:
        lead_id = save_lead(
            name      = name,
            email     = email,
            phone     = caller_phone,
            project   = project,
            budget    = budget,
            idea      = idea,
            ip        = caller_phone,
            source    = "call",
            scheduled = scheduled,
        )
        save_call_log(call_id, caller_phone, transcript, lead_id)
        logger.info(f"Call lead #{lead_id} saved — {name} | {email}")

        send_notification_email(
            lead_id, name, email, caller_phone,
            project, budget,
            f"[Phone call via Vapi AI]\n\n{idea}",
            "call", scheduled, now,
        )
        send_confirmation_email(name, email, project, "call", scheduled)

    except Exception as exc:
        logger.error(f"Call lead save failed: {exc}")


# ══════════════════════════════════════════════════════════════
#  ROUTES — Admin Dashboards
# ══════════════════════════════════════════════════════════════

@app.route("/admin/leads")
def view_leads():
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ORDER BY id DESC")
    rows   = cursor.fetchall()
    conn.close()

    rows_html = ""
    for row in rows:
        id_, name, email, phone, project, budget, idea, ip, source, scheduled, status, submitted = row
        idea_short  = (idea[:80] + "…") if idea and len(idea) > 80 else (idea or "—")
        src_cls     = "badge-call" if source == "call" else "badge-web"
        src_ico     = "[C]" if source == "call" else "[W]"
        sched_cell  = f'<span style="color:#f59e0b;font-size:.65rem;">📅 {scheduled}</span>' \
                      if scheduled and scheduled != "Not scheduled" else "—"
        rows_html += f"""
        <tr>
          <td><strong style="color:#0ea5e9;">{id_}</strong></td>
          <td><strong>{name}</strong></td>
          <td><a href="mailto:{email}">{email}</a></td>
          <td>{phone or '—'}</td>
          <td>{project or '—'}</td>
          <td>{budget or '—'}</td>
          <td title="{idea or ''}">{idea_short}</td>
          <td>{sched_cell}</td>
          <td><span class="{src_cls}">{src_ico} {source}</span></td>
          <td style="white-space:nowrap;color:#64748b;font-size:.65rem;">{submitted}</td>
        </tr>"""

    empty = ('<tr><td colspan="10" style="text-align:center;padding:60px;color:#4a6080;">'
             'No leads yet — share your site!</td></tr>') if not rows else ""

    return _admin_page(
        title    = "BuildSpark — Leads",
        heading  = "Leads Database",
        subhead  = "All leads from web forms and phone calls",
        count    = f"{len(rows)} TOTAL LEADS",
        active   = "leads",
        headers  = ["#","Name","Email","Phone","Project","Budget",
                    "Idea","Scheduled","Source","Submitted At"],
        body     = rows_html + empty,
        accent   = "#0ea5e9",
    )


@app.route("/admin/calls")
def view_calls():
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM call_logs ORDER BY id DESC")
    rows   = cursor.fetchall()
    conn.close()

    rows_html = ""
    for row in rows:
        id_, call_id, phone, lead_id, transcript, started = row
        preview = (transcript[:120] + "…") if transcript and len(transcript) > 120 \
                  else (transcript or "—")
        rows_html += f"""
        <tr>
          <td><strong style="color:#f59e0b;">{id_}</strong></td>
          <td style="font-size:.6rem;color:#4a6080;">{call_id or '—'}</td>
          <td>{phone or '—'}</td>
          <td>{'Lead #' + str(lead_id) if lead_id else '—'}</td>
          <td title="{transcript or ''}">{preview}</td>
          <td style="white-space:nowrap;color:#64748b;font-size:.65rem;">{started}</td>
        </tr>"""

    empty = ('<tr><td colspan="6" style="text-align:center;padding:60px;color:#4a6080;">'
             'No calls yet.</td></tr>') if not rows else ""

    return _admin_page(
        title   = "📞 BuildSpark — Calls",
        heading = "📞 Call Logs",
        subhead = "All inbound AI agent calls via Vapi",
        count   = f"{len(rows)} CALLS",
        active  = "calls",
        headers = ["#","Call ID","Caller Phone","Lead","Transcript Preview","Started At"],
        body    = rows_html + empty,
        accent  = "#f59e0b",
    )


def _admin_page(title, heading, subhead, count, active,
                headers, body, accent="#0ea5e9"):
    """Shared admin page template."""
    ths = "".join(f"<th>{h}</th>" for h in headers)
    return f"""<!DOCTYPE html>
<html><head><title>{title}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'Courier New',monospace;background:#060b12;color:#e2e8f0;padding:40px;}}
  h1{{font-size:1.5rem;color:{accent};margin-bottom:6px;}}
  .sub{{font-size:.7rem;color:#4a6080;margin-bottom:28px;}}
  .nav{{display:flex;gap:12px;margin-bottom:24px;align-items:center;}}
  .cnt{{background:{accent};color:{'#060b12' if accent=='#f59e0b' else 'white'};
        font-size:.68rem;padding:4px 14px;border-radius:2px;letter-spacing:.1em;margin-right:4px;}}
  .btn{{background:rgba(14,165,233,.1);color:#0ea5e9;border:1px solid rgba(14,165,233,.25);
        padding:6px 16px;font-family:'Courier New',monospace;font-size:.65rem;
        letter-spacing:.1em;text-transform:uppercase;text-decoration:none;border-radius:2px;}}
  .btn:hover{{background:rgba(14,165,233,.2);}}
  .btn.on{{background:{accent};color:{'#060b12' if accent=='#f59e0b' else 'white'};border-color:{accent};}}
  .wrap{{overflow-x:auto;}}
  table{{width:100%;border-collapse:collapse;font-size:.7rem;}}
  th{{background:{accent};color:{'#060b12' if accent=='#f59e0b' else 'white'};
      padding:12px 14px;text-align:left;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap;}}
  td{{padding:11px 14px;border-bottom:1px solid rgba(14,165,233,.08);
      vertical-align:top;max-width:260px;word-wrap:break-word;}}
  tr:hover td{{background:rgba(14,165,233,.04);}}
  .badge-web{{background:rgba(16,185,129,.12);color:#10b981;border:1px solid rgba(16,185,129,.25);
              padding:2px 8px;border-radius:2px;font-size:.6rem;}}
  .badge-call{{background:rgba(245,158,11,.12);color:#f59e0b;border:1px solid rgba(245,158,11,.25);
               padding:2px 8px;border-radius:2px;font-size:.6rem;}}
  a{{color:#0ea5e9;text-decoration:none;}}
  a:hover{{text-decoration:underline;}}
  .back{{display:block;margin-bottom:24px;color:#0ea5e9;font-size:.68rem;
         letter-spacing:.1em;text-transform:uppercase;width:fit-content;}}
</style></head>
<body>
  <a href="/" class="back">← Back to Website</a>
  <h1>{heading}</h1>
  <p class="sub">{subhead}</p>
  <div class="nav">
    <span class="cnt">{count}</span>
    <a href="/admin/leads" class="btn {'on' if active=='leads' else ''}">📋 Leads</a>
    <a href="/admin/calls" class="btn {'on' if active=='calls' else ''}">📞 Call Logs</a>
  </div>
  <div class="wrap">
    <table>
      <thead><tr>{ths}</tr></thead>
      <tbody>{body}</tbody>
    </table>
  </div>
</body></html>"""


# ══════════════════════════════════════════════════════════════
#  Start
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    print("""
╔══════════════════════════════════════════════════════════╗
║             BuildSpark is Running! ⚡                    ║
║                                                          ║
║  Website:       http://localhost:5000                    ║
║  Leads:         http://localhost:5000/admin/leads        ║
║  Call Logs:     http://localhost:5000/admin/calls        ║
║                                                          ║
║  Vapi webhook:  https://<ngrok-url>/vapi/chat            ║
║  Vapi end hook: https://<ngrok-url>/vapi/end             ║
╚══════════════════════════════════════════════════════════╝
""")
    app.run(host="0.0.0.0", port=5000, debug=True)