# AI Analyst setup

The FastAPI backend reads Gemini configuration from its process environment or a root `.env` file. `.env` is ignored by Git. Never add the Gemini key to a `NEXT_PUBLIC_` variable.

Copy `.env.example` to `.env`, set `AI_ENABLED=true`, and add a Gemini Developer API key:

```env
AI_ENABLED=true
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.5-flash-lite
```

Restart the FastAPI backend after changing environment values. `GEMINI_MODEL` can select another model available to the configured account. The default `gemini-3.5-flash` was verified with live Gemini requests. The service uses Google's Python `google-genai` SDK asynchronous `generate_content` operation; it sends a bounded transcript and compact, question-relevant MethaTrace context. If AI is disabled or no key is configured, `/api/ai/chat` returns a clear 503 response and does not invent an answer.

Risk scores and factor contributions are calculated by the existing backend risk engine. Methane observations remain identified as synthetic and sensor readings as simulated.
