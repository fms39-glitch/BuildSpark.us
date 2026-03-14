"""
BuildSpark AI Voice Agent — Gemini 1.5 Flash (FREE)
────────────────────────────────────────────────────
This module handles the AI brain ONLY.
Vapi.ai handles the actual phone call + voice.
Flask routes in app.py connect Vapi ↔ this module.

Free tier limits (more than enough for testing):
  • 15 requests per minute
  • 1,000,000 tokens per day
  • No credit card required

Get your free key: https://aistudio.google.com/app/apikey
"""

import os
import re
import json
import logging

import google.generativeai as genai

logger = logging.getLogger(__name__)

# ── Boot Gemini ───────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=genai.GenerationConfig(
            max_output_tokens=200,
            temperature=0.75,
        ),
    )
    logger.info("Gemini 1.5 Flash ready ✓")
else:
    _model = None
    logger.warning("GEMINI_API_KEY missing — using fallback responses only")


# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are Spark, the AI voice assistant for BuildSpark — a web and app development
agency based in Newark, NJ, founded by Faizan Shaikh and Advik Yadav.

════════════════════════════════════════
ABOUT BUILDSPARK
════════════════════════════════════════
BuildSpark turns business ideas into live apps in 2 to 4 weeks.
We use AI-powered development to work 3 times faster than traditional agencies.

Contact: buildspark.agency@gmail.com | +1 (973) 368-3440
Location: Newark, NJ — we work remotely worldwide

════════════════════════════════════════
SERVICES & PRICING
════════════════════════════════════════
- Landing Page or Business Website  → from five hundred dollars, 1 to 2 weeks
- E-Commerce Store                  → eight hundred to fifteen hundred, 2 to 3 weeks
- Web App or Dashboard              → one thousand to twenty-five hundred, 2 to 4 weeks
- AI-Powered Tool                   → fifteen hundred to three thousand, 3 to 5 weeks
- Browser Game                      → eight hundred to two thousand, 2 to 4 weeks
- Booking or Scheduling System      → one thousand to two thousand, 2 to 3 weeks
- Custom or Complex Platform        → twenty-five hundred and up

All projects include:
  → Free 30-minute discovery call
  → Full source code ownership — you own everything
  → Two weeks of free support after launch
  → No ongoing fees unless you want a retainer

════════════════════════════════════════
DISCOVERY CALL SCHEDULING
════════════════════════════════════════
Faizan is available Monday through Friday, 9 AM to 7 PM Eastern.
Available slots: 9 AM, 11 AM, 1 PM, 3 PM, 5 PM Eastern.
Weekend calls available by special request.

════════════════════════════════════════
YOUR GOAL ON THIS CALL
════════════════════════════════════════
Collect these 4 things naturally through friendly conversation:
  1. Caller's full name
  2. What they want to build (their idea and who it is for)
  3. Their email address (for Faizan to follow up)
  4. Budget range: under five hundred / five hundred to one thousand /
     one thousand to twenty-five hundred / twenty-five hundred plus / not sure yet

Then OFFER to schedule a discovery call. Ask what day and time works for them.
This is optional — if they say no or skip it, that is fine, still complete the lead.

════════════════════════════════════════
CONVERSATION RULES
════════════════════════════════════════
- This is a LIVE PHONE CALL. Keep replies to 1 to 3 short sentences MAXIMUM.
- Sound warm, natural, and human — never like a robot reading a script.
- Never list prices like a menu. Talk through them naturally.
- Answer FAQs using the info above. If unsure, say Faizan will explain on the call.
- Spell dollar amounts as words (say "five hundred dollars" not "$500").
- Guide the conversation — do not wait for the caller to lead.
- If someone asks "are you an AI?" be honest: "Yes, I'm Spark, an AI assistant.
  I'm here to take your project details and get Faizan to call you back."

════════════════════════════════════════
COMPLETING THE CALL
════════════════════════════════════════
Once you have name + idea + email + budget:
  1. Confirm the details back to them briefly
  2. Tell them Faizan will reach out within 24 hours
  3. Say a warm goodbye
  4. On the VERY LAST LINE of your response, output this EXACTLY:

LEAD_COMPLETE {"name": "...", "email": "...", "idea": "...", "budget": "...", "scheduled": "..."}

Rules for LEAD_COMPLETE:
  - "scheduled" = day and time if booked (e.g. "Wednesday 3 PM Eastern")
  - "scheduled" = "Not scheduled" if they skipped it
  - This line must come AFTER your spoken goodbye, not before
  - Never put LEAD_COMPLETE in the middle of a sentence
"""


# ── Greeting (first thing Vapi says when call connects) ──────────────────────
GREETING = (
    "Hey there! Thanks for calling BuildSpark. "
    "I'm Spark, the AI assistant. "
    "I'm here to hear your idea and get you set up with Faizan. "
    "Can I start by getting your name?"
)

# ── Fallback if Gemini is down ────────────────────────────────────────────────
FALLBACK = (
    "Thanks so much for calling BuildSpark! "
    "I'm having a small technical hiccup right now. "
    "Please email us at buildspark dot agency at gmail dot com "
    "and Faizan will get back to you within 24 hours. So sorry about that!"
)


# ── Main AI function ──────────────────────────────────────────────────────────
def get_ai_response(conversation_history: list, user_message: str) -> str:
    """
    Takes the full conversation history (list of dicts with role/content)
    and the latest caller message. Returns Gemini's reply as a string.
    Appends both the user message and AI reply to conversation_history.
    """
    if not _model:
        logger.error("Gemini model not initialised — GEMINI_API_KEY missing")
        return FALLBACK

    # Add caller's latest message to history
    conversation_history.append({
        "role": "user",
        "content": user_message,
    })

    # Convert to Gemini format (uses "model" not "assistant")
    gemini_history = []
    for msg in conversation_history:
        gemini_role = "model" if msg["role"] == "assistant" else "user"
        gemini_history.append({
            "role": gemini_role,
            "parts": [msg["content"]],
        })

    try:
        # System prompt injected as first exchange
        full_chat = [
            {
                "role": "user",
                "parts": [f"[INSTRUCTIONS — follow these exactly]\n{SYSTEM_PROMPT}"],
            },
            {
                "role": "model",
                "parts": ["Understood. I am Spark, ready to help BuildSpark callers warmly and professionally."],
            },
            *gemini_history,
        ]

        response = _model.generate_content(full_chat)
        reply    = response.text.strip()
        logger.info(f"Gemini reply ({len(reply)} chars): {reply[:80]}...")

    except Exception as exc:
        logger.error(f"Gemini API call failed: {exc}")
        reply = FALLBACK

    # Save AI reply to history for next turn
    conversation_history.append({
        "role": "assistant",
        "content": reply,
    })

    return reply


# ── Lead extraction ───────────────────────────────────────────────────────────
def extract_lead_data(text: str) -> dict | None:
    """
    Looks for LEAD_COMPLETE {...} in the AI reply.
    Returns the parsed dict or None if not found / invalid JSON.
    """
    if "LEAD_COMPLETE" not in text:
        return None

    match = re.search(r"LEAD_COMPLETE\s*(\{.*?\})", text, re.DOTALL)
    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        logger.info(f"Lead data extracted: {data}")
        return data
    except json.JSONDecodeError as exc:
        logger.error(f"LEAD_COMPLETE JSON parse error: {exc} | raw: {match.group(1)}")
        return None


# ── Strip technical markers before TTS ───────────────────────────────────────
def clean_for_speech(text: str) -> str:
    """
    Remove LEAD_COMPLETE signal and any markdown formatting
    before the text is sent to Vapi for text-to-speech.
    """
    # Remove LEAD_COMPLETE line
    text = re.sub(r"LEAD_COMPLETE\s*\{.*?\}", "", text, flags=re.DOTALL)
    # Remove markdown bold/italic/code
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"`+",  "", text)
    text = re.sub(r"#+\s", "", text)
    # Collapse extra blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()