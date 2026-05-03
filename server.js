import express from 'express';
import Anthropic from '@anthropic-ai/sdk';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
const client = new Anthropic();

app.use(express.json());
app.use(express.static(join(__dirname, 'public')));

const SYSTEM_PROMPT = `You are an elite Human Resources strategist and personal development coach with deep expertise in career design, strengths assessment, and opportunity mapping. Your role is to guide the user through a structured discovery process based on the Ikigai framework — finding the intersection between what they love, what they are good at, what the world needs, and what they can be paid for.

Tone: Warm, direct, and informal. Address the user as "you" but with the closeness of a trusted advisor — never stiff, never generic. Be human.

Approach: Blend coaching and consulting. Ask thoughtful, Socratic questions to provoke genuine reflection, but also offer direct observations and patterns when you spot them. Be rigorous but never clinical. Never rush — depth matters more than speed.

Process: Guide the user through the four Ikigai dimensions one at a time, in natural conversation. Adapt your questions based on their answers. Do not move to the next dimension until you have meaningful material. When you have enough across all four, synthesize.

Rules: Keep a broad perspective. Never assume the user's current profession defines them. Challenge assumptions gently. The goal is clarity, not confirmation.

IMPORTANT: Keep responses concise and focused — 2-4 short paragraphs max per message. Ask one question at a time. Let the conversation breathe.`;

const SYNTHESIS_SYSTEM = `You are an expert at synthesizing Ikigai frameworks from conversations. Analyze the full conversation provided and return ONLY a valid JSON object — no prose, no markdown, no code fences. Just the raw JSON.

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

Generate 4-6 opportunities. Make them concrete, specific, and genuinely tailored.`;

// Streaming chat endpoint
app.post('/api/chat', async (req, res) => {
  const { messages } = req.body;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('Access-Control-Allow-Origin', '*');

  try {
    const stream = client.messages.stream({
      model: 'claude-sonnet-4-6',
      max_tokens: 1024,
      system: SYSTEM_PROMPT,
      messages,
    });

    stream.on('text', (text) => {
      res.write(`data: ${JSON.stringify({ text })}\n\n`);
    });

    stream.on('finalMessage', () => {
      res.write('data: [DONE]\n\n');
      res.end();
    });

    stream.on('error', (err) => {
      console.error('Stream error:', err);
      res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`);
      res.end();
    });
  } catch (error) {
    console.error('Chat error:', error);
    res.write(`data: ${JSON.stringify({ error: error.message })}\n\n`);
    res.end();
  }
});

// Synthesis endpoint — returns full Ikigai JSON
app.post('/api/synthesize', async (req, res) => {
  const { messages } = req.body;

  try {
    const response = await client.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 4096,
      system: SYNTHESIS_SYSTEM,
      messages: [
        ...messages,
        {
          role: 'user',
          content: 'Please synthesize our entire conversation now and produce the complete Ikigai analysis JSON.',
        },
      ],
    });

    const raw = response.content[0].text.trim();
    // Strip any accidental markdown fences
    const clean = raw.replace(/^```json\n?/, '').replace(/^```\n?/, '').replace(/\n?```$/, '');
    const data = JSON.parse(clean);
    res.json(data);
  } catch (error) {
    console.error('Synthesis error:', error);
    res.status(500).json({ error: error.message });
  }
});

// Welcome message — first message from the AI
app.get('/api/welcome', async (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  try {
    const stream = client.messages.stream({
      model: 'claude-sonnet-4-6',
      max_tokens: 512,
      system: SYSTEM_PROMPT,
      messages: [
        {
          role: 'user',
          content: 'Hello, I want to discover my Ikigai.',
        },
      ],
    });

    stream.on('text', (text) => {
      res.write(`data: ${JSON.stringify({ text })}\n\n`);
    });

    stream.on('finalMessage', () => {
      res.write('data: [DONE]\n\n');
      res.end();
    });

    stream.on('error', (err) => {
      res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`);
      res.end();
    });
  } catch (error) {
    res.write(`data: ${JSON.stringify({ error: error.message })}\n\n`);
    res.end();
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`\n✦ Ikigai Coach running → http://localhost:${PORT}\n`);
});
