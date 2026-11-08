# MethaTrace frontend

This folder contains the Next.js frontend. For the full Next.js + FastAPI development setup, Gemini configuration, API health check, and test commands, see the [repository README](../README.md).

To run the frontend independently:

```powershell
npm install
npm run dev
```

The frontend expects FastAPI at `http://127.0.0.1:8000` unless `NEXT_PUBLIC_API_URL` is set in `frontend/.env.local`.
