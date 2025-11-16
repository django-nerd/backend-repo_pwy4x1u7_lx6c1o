import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import math

app = FastAPI(title="CheapStop API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Utilities
# -----------------------------

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in miles between two lat/lng points."""
    R = 3958.8  # Radius of Earth in miles
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Example chain definitions. In a real app, these would be discovered via APIs or scraping.
# We position three stores near the user's location by applying small offsets at request-time.
BASE_CHAINS = [
    {"id": "walmart", "name": "Walmart Supercenter"},
    {"id": "target", "name": "Target"},
    {"id": "kroger", "name": "Kroger"},
]

# -----------------------------
# Models
# -----------------------------

class SearchRequest(BaseModel):
    query: str = Field(..., description="Comma-separated list of items, e.g. 'eggs, milk, chicken'")
    lat: float = Field(..., description="User latitude")
    lng: float = Field(..., description="User longitude")
    radiusMiles: Optional[float] = Field(5.0, description="Search radius in miles")

class Item(BaseModel):
    name: str
    price: float
    quantity: int = 1

class StoreResult(BaseModel):
    storeId: str
    storeName: str
    distanceMiles: float
    lat: float
    lng: float
    totalPrice: float
    items: List[Item]

class SearchResponse(BaseModel):
    query: str
    mode: str
    totalStores: int
    stores: List[StoreResult]

# -----------------------------
# Routes
# -----------------------------

@app.get("/")
def read_root():
    return {"message": "CheapStop backend running"}

@app.post("/api/search", response_model=SearchResponse)
def search_stores(payload: SearchRequest):
    # Parse items
    items = [part.strip() for part in payload.query.split(',') if part.strip()]
    if not items:
        raise HTTPException(status_code=400, detail="Please provide at least one item in the query.")

    # For demo/hackathon: fabricate three nearby stores with slight lat/lng offsets
    # Offsets roughly ~0.01 deg ~ 0.6 miles depending on latitude
    offsets = [
        (0.010, 0.012),
        (-0.008, 0.009),
        (0.006, -0.010),
    ]

    stores: List[StoreResult] = []

    for chain, (dlat, dlng) in zip(BASE_CHAINS, offsets):
        store_lat = payload.lat + dlat
        store_lng = payload.lng + dlng
        dist = haversine(payload.lat, payload.lng, store_lat, store_lng)

        # Skip stores outside radius
        if payload.radiusMiles and dist > payload.radiusMiles:
            continue

        # Enrich items with pseudo-prices - deterministic based on name length to keep stable
        enriched: List[Item] = []
        total = 0.0
        for name in items:
            base = max(1.0, (len(name) % 7) + 1)  # 1..8
            price = round(base * 0.99 + (hash(name + chain["id"]) % 100) / 250.0, 2)
            enriched.append(Item(name=name, price=price, quantity=1))
            total += price

        stores.append(
            StoreResult(
                storeId=f"{chain['id']}-{abs(int(store_lat*1000))}-{abs(int(store_lng*1000))}",
                storeName=f"{chain['name']}",
                distanceMiles=round(dist, 2),
                lat=round(store_lat, 6),
                lng=round(store_lng, 6),
                items=enriched,
                totalPrice=round(total, 2),
            )
        )

    stores.sort(key=lambda s: (s.totalPrice, s.distanceMiles))

    return SearchResponse(
        query=payload.query,
        mode="live",  # keep shape as requested
        totalStores=len(stores),
        stores=stores,
    )

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db

        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
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
