# kovacsik_algo

FastAPI webhook that receives inbound emails (via Mailgun/Postmark/SendGrid/Zapier),
classifies them with OpenAI, and optionally places BUY orders on Interactive Brokers.

## Deploy on Railway
1. Push this repo to GitHub.
2. On Railway: New Project ? Deploy from GitHub ? select `kovacsik_algo`.
3. Add environment variables from `.env.example` in Railway ? Variables.
4. Deploy. Note the public URL (e.g. `https://<project>.up.railway.app`).

## Connect email ? webhook
Use any of these:
- Mailgun Inbound Routes ? forward to `POST https://<your-url>/email-inbound`
- Postmark Inbound ? webhook to `/email-inbound`
- SendGrid Inbound Parse ? webhook to `/email-inbound`
- Zapier/Make ? send payload to `/email-inbound`

Map fields so the webhook receives `from`, `subject`, and `stripped-text`/`text`.

## IBKR
- Start **IB Gateway** or **TWS** with API enabled.
- Ensure the Railway app can reach `IB_HOST:IB_PORT`. If your Gateway is on a private network,
  use a secure tunnel or host Gateway on a reachable server.
- Start with `DRY_RUN=true`. Switch to `false` only when ready.

## Local dev
```bash
pip install -r requirements.txt
export $(cat .env | xargs)  # or use python-dotenv
uvicorn main:app --reload
