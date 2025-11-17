import os
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import ReturnDocument

from database import db

app = FastAPI(title="COTY - Coin of the Year API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Models ----
class VoteRequest(BaseModel):
    symbol: str


# ---- Helpers ----
COINS_PRESET = [
    {"name": "Bitcoin", "symbol": "BTC", "color": "#f59e0b"},
    {"name": "Ethereum", "symbol": "ETH", "color": "#60a5fa"},
    {"name": "Solana", "symbol": "SOL", "color": "#34d399"},
    {"name": "Cardano", "symbol": "ADA", "color": "#93c5fd"},
    {"name": "Polkadot", "symbol": "DOT", "color": "#f472b6"},
    {"name": "Chainlink", "symbol": "LINK", "color": "#60a5fa"},
]


def initialize_coins():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    col = db["coin"]
    # Ensure each coin exists; do not reset votes
    for c in COINS_PRESET:
        col.update_one(
            {"symbol": c["symbol"]},
            {"$setOnInsert": {"name": c["name"], "color": c.get("color"), "votes": 0}},
            upsert=True,
        )


def serialize_coin(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": doc.get("name"),
        "symbol": doc.get("symbol"),
        "votes": int(doc.get("votes", 0)),
        "color": doc.get("color"),
    }


def get_leaderboard() -> Dict[str, Any]:
    initialize_coins()
    coins = list(db["coin"].find({}, {"_id": 0}).sort("votes", -1))
    total_votes = sum(int(c.get("votes", 0)) for c in coins)
    leader = coins[0]["symbol"] if coins else None
    # Rank coins
    ranked = []
    for idx, c in enumerate(coins, start=1):
        ranked.append({**serialize_coin(c), "rank": idx})
    return {"coins": ranked, "totalVotes": int(total_votes), "leader": leader}


# ---- Routes ----
@app.on_event("startup")
def on_startup():
    try:
        initialize_coins()
    except Exception:
        # If DB isn't available on cold start, endpoints will surface error later
        pass


@app.get("/")
def read_root():
    return {"message": "COTY API is running"}


@app.get("/api/coins")
def list_coins():
    """Return coins with current vote counts and leaderboard info"""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    return get_leaderboard()


@app.post("/api/vote")
def vote(req: VoteRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    symbol = req.symbol.upper().strip()
    updated = db["coin"].find_one_and_update(
        {"symbol": symbol},
        {"$inc": {"votes": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Coin not found")

    # Return updated leaderboard
    return get_leaderboard()


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
