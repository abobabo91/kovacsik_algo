import os
import json
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from openai import OpenAI
from ib_insync import IB, Stock, MarketOrder

from dotenv import load_dotenv

# --------- Config via env ----------
load_dotenv("./secrets.env", override=False)


OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
MODEL            = os.getenv("OPENAI_MODEL", "gpt-5-nano")

# IBKR
IB_HOST          = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT          = int(os.getenv("IB_PORT", "7497"))   # 7497 paper, 7496 live
IB_CLIENT_ID     = int(os.getenv("IB_CLIENT_ID", "42"))
DEFAULT_QTY      = int(os.getenv("DEFAULT_BUY_QTY", "10"))
DEFAULT_EXCHANGE = os.getenv("DEFAULT_EXCHANGE", "SMART")
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "USD")

# Safety toggles
DRY_RUN          = os.getenv("DRY_RUN", "true").lower() in ("1","true","yes","on")
SYMBOL_ALLOWLIST = {s.strip().upper() for s in os.getenv("SYMBOL_ALLOWLIST", "").split(",") if s.strip()}

app = FastAPI()

# --------- Global clients ----------
oa = OpenAI(api_key=OPENAI_API_KEY)

ib: IB | None = None
def ensure_ib() -> IB:
    global ib
    if DRY_RUN:
        return None  # skip actual trading
    if ib is None or not ib.isConnected():
        ib = IB()
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID)
    return ib

# --------- Helpers ----------
def build_prompt(meta: Dict[str, str]) -> tuple[str, str]:
    sys = (
        "You are a strict financial email classifier. "
        "Return ONLY JSON with keys: buy (boolean), symbol (string), qty (integer), reason (string). "
        "Only true BUY signals for listed US stocks. If symbol is unclear, set symbol to ''. "
        "If quantity is missing, infer a reasonable integer or 0."
    )
    user = (
        f"From: {meta['sender']}\n"
        f"Subject: {meta['subject']}\n\n"
        f"{meta['body']}\n\n"
        "Return only JSON."
    )
    return sys, user

def call_openai(sys: str, user: str) -> dict:
    try:
        resp = oa.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ]
            # NOTE: no temperature here; some models only accept default=1
        )
        try:
            out = json.loads(resp.choices[0].message.content)
        except Exception:
            out = {"buy": False, "symbol": "", "qty": 0, "reason": "ParseError"}
    except Exception as e:
        return {"buy": False, "symbol": "", "qty": 0, "reason": f"OpenAIError: {type(e).__name__}: {e}"}

    out.setdefault("buy", False)
    out.setdefault("symbol", "")
    out.setdefault("qty", 0)
    out.setdefault("reason", "")
    try:
        qty = int(out["qty"])
        out["qty"] = qty if qty > 0 else DEFAULT_QTY
    except Exception:
        out["qty"] = DEFAULT_QTY
    out["symbol"] = (out["symbol"] or "").upper().strip()
    return out


def allowed_symbol(symbol: str) -> bool:
    if not symbol:
        return False
    if SYMBOL_ALLOWLIST:
        return symbol in SYMBOL_ALLOWLIST
    return True

def place_buy(symbol: str, qty: int) -> Dict[str, Any]:
    if DRY_RUN:
        return {"dry_run": True, "action": "BUY", "symbol": symbol, "qty": qty}
    broker = ensure_ib()
    contract = Stock(symbol, DEFAULT_EXCHANGE, DEFAULT_CURRENCY)
    order = MarketOrder("BUY", qty)
    trade = broker.placeOrder(contract, order)
    trade.waitUntilDone(timeout=30)
    return {
        "dry_run": False,
        "status": getattr(trade.orderStatus, "status", "UNKNOWN"),
        "filled": getattr(trade.orderStatus, "filled", None),
        "avgPrice": getattr(trade.orderStatus, "avgFillPrice", None),
        "orderId": getattr(trade.order, "orderId", None),
        "symbol": symbol,
        "qty": qty,
    }


def normalize_inbound_payload(data: Dict[str, Any]) -> Dict[str, str]:
    sender = data.get("from") or ""
    subject = data.get("subject") or ""
    body = data.get("text") or ""
    return {
        "sender": sender.strip(),
        "subject": subject.strip(),
        "body": body.strip(),
    }


@app.post("/email-inbound")
async def email_inbound(req: Request):
    try:
        ctype = (req.headers.get("content-type") or "").lower()
        raw = await req.body()

        # Handle form-data or x-www-form-urlencoded
        if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
            form = await req.form()
            data = dict(form)
        else:
            try:
                data = await req.json()
            except Exception:
                try:
                    data = json.loads(raw.decode("utf-8", errors="ignore"))
                except Exception:
                    data = {}

        print("RAW BODY:", raw.decode("utf-8", errors="ignore"), flush=True)
        print("PARSED DATA:", data, flush=True)

        meta = normalize_inbound_payload(data)
        print("INBOUND:", {
            "from": meta["sender"],
            "subject": meta["subject"],
            "has_text": bool(meta["body"]),
        }, flush=True)

        sys, user = build_prompt(meta)
        decision = call_openai(sys, user)

        result = {"decision": decision, "executed": False}
        if decision.get("buy") and allowed_symbol(decision.get("symbol", "")):
            result["trade"] = place_buy(decision["symbol"], int(decision["qty"]))
            result["executed"] = True
        else:
            result["reason"] = decision.get("reason", "Not a BUY or symbol not allowed")

        return JSONResponse(result)

    except Exception as e:
        print("ERROR handling /email-inbound:", e, flush=True)
        return JSONResponse({"error": str(e)}, status_code=500)




@app.get("/")
def health():
    return {"ok": True, "service": "email->gpt->ibkr", "dry_run": DRY_RUN}


@app.get("/debug/openai")
def debug_openai():
    try:
        resp = oa.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Ping"}]
        )
        sample = resp.choices[0].message.content.strip()
        return {"ok": True, "model": MODEL, "response": sample[:40]}
    except Exception as e:
        return {"ok": False, "model": MODEL, "error": f"{type(e).__name__}: {e}"}



