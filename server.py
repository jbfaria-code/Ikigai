import json
import os
import re

import anthropic
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

app = Flask(__name__, static_folder="public")
client = anthropic.Anthropic()

# OpenAI TTS — only initialise if key is present
try:
    from openai import OpenAI
    openai_client = OpenAI() if os.environ.get("OPENAI_API_KEY") else None
except ImportError:
    openai_client = None

SYSTEM_PROMPT = """You are an elite Human Resources strategist and personal development coach with deep expertise in career design, strengths assessment, and opportunity mapping. Your role is to guide the user through a structured discovery process based on the Ikigai framework — finding the intersection between what they love, what they are good at, what the world needs, and what they can be paid for.

Tone: Warm, direct, and informal. Address the user as "you" but with the closeness of a trusted advisor — never stiff, never generic. Be human.

Approach: Blend coaching and consulting. Ask thoughtful, Socratic questions to provoke genuine reflection, but also offer direct observations and patterns when you spot them. Be rigorous but never clinical. Never rush — depth matters more than speed.

Process: Guide the user through the four Ikigai dimensions one at a time, in natural conversation. Adapt your questions based on their answers. Do not move to the next dimension until you have meaningful material. When you have enough across all four, synthesize.

Rules: Keep a broad perspective. Never assume the user's current profession defines them. Challenge assumptions gently. The goal is clarity, not confirmation.

IMPORTANT: Keep responses concise and focused — 2-4 short paragraphs max per message. Ask one question at a time. Let the conversation breathe."""

SYNTHESIS_SYSTEM = """You are an expert at synthesizing Ikigai frameworks from conversations. Analyze the full conversation provided and return ONLY a valid JSON object — no prose, no markdown, no code fences. Just the raw JSON.

The JSON must follow this exact structure:
{
  "ikigai_map": {
    "love": ["3-6 specific things they love, each under 8 words"],
    "good_at": ["3-6 specific strengths or skills, each under 8 words"],
    "world_needs": ["3-6 needs they can address, each under 8 words"],
    "paid_for": ["3-6 ways they can monetize, each under 8 words"]
  },
  "intersections": {
    "passion": "One sentence: Love meets Good At",
    "profession": "One sentence: Good At meets Paid For",
    "mission": "One sentence: Love meets World Needs",
    "vocation": "One sentence: World Needs meets Paid For",
    "ikigai": "One powerful sentence capturing the center — their core Ikigai"
  },
  "report": "A 400-600 word professional assessment. Use line breaks between paragraphs (\\n\\n). Be specific to what they shared. Include: key patterns, your direct observations, what makes them unique, and what could hold them back. Be warm but candid.",
  "opportunities": [
    {
      "title": "Specific role, venture, or project title",
      "type": "Job | Freelance | Business | Project | Side Hustle",
      "description": "2-3 sentences on what this looks like concretely — what they would do day-to-day",
      "why": "Why this sits at their Ikigai center — link to specific things they shared"
    }
  ]
}

Generate 4-6 opportunities. Make them concrete, specific, and genuinely tailored."""


def stream_messages(messages, system=SYSTEM_PROMPT, max_tokens=1024):
    """Yield SSE chunks from a streaming Anthropic call."""
    @stream_with_context
    def generate():
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    payload = json.dumps({"text": text})
                    yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            print(f"Stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.route("/api/tts", methods=["POST"])
def tts():
    if not openai_client:
        return jsonify({"error": "TTS not configured"}), 503

    text = request.json.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    # Clean markdown and limit length for speed
    clean = re.sub(r'[*_`#>]', '', text)
    clean = re.sub(r'\n+', ' ', clean).strip()
    clean = clean[:900]  # keep responses snappy

    audio = openai_client.audio.speech.create(
        model="tts-1",
        voice="nova",   # warm, natural-sounding voice
        input=clean,
    )

    return Response(
        audio.content,
        mimetype="audio/mpeg",
        headers={"Content-Type": "audio/mpeg"},
    )


@app.route("/")
def index():
    return send_from_directory("public", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("public", path)


@app.route("/api/welcome", methods=["GET", "POST"])
def welcome():
    messages = [{"role": "user", "content": "Hello, I want to discover my Ikigai."}]
    return stream_messages(messages, max_tokens=512)


@app.route("/api/chat", methods=["POST"])
def chat():
    messages = request.json.get("messages", [])
    return stream_messages(messages)


@app.route("/api/synthesize", methods=["POST"])
def synthesize():
    messages = request.json.get("messages", [])
    synthesis_messages = messages + [{
        "role": "user",
        "content": "Please synthesize our entire conversation now and produce the complete Ikigai analysis JSON."
    }]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYNTHESIS_SYSTEM,
        messages=synthesis_messages,
    )

    raw = response.content[0].text.strip()
    clean = re.sub(r"^```json\n?", "", raw)
    clean = re.sub(r"^```\n?", "", clean)
    clean = re.sub(r"\n?```$", "", clean)

    data = json.loads(clean)
    return jsonify(data)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"\n✦ Ikigai Coach running → http://localhost:{port}\n")
    app.run(port=port, debug=False)
