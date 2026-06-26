import os
import math
import joblib
import json
import redis
import numpy as np
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Real-Time Credit Card Fraud Detector",
    description="FastAPI microservice utilizing Random Forest and Redis to score transaction risks.",
    version="1.1.0"
)

# 1. Connect to Redis database (production low-latency feature cache)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

print(f"Connecting to Redis Feature Cache at {REDIS_HOST}:{REDIS_PORT}...")
r_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

# 2. Load model artifacts
try:
    rf_model = joblib.load("models/random_forest_model.pkl")
    label_encoder = joblib.load("models/label_encoder.pkl")
    with open("models/user_profiles.json", "r") as f:
        user_profiles = json.load(f)
    print("Model artifacts loaded successfully.")
except Exception as e:
    print(f"Error loading model artifacts: {e}")
    rf_model = None

def get_haversine_distance(lat1, lon1, lat2, lon2):
    """
    Haversine algorithm tracking spatial distance in kilometers between 
    a consumer's home coordinates and the vendor's physical location.
    """
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

# Request Input Schema
class TransactionRequest(BaseModel):
    transaction_id: str = Field(..., example="tx_192837465")
    cc_num: int = Field(..., example=4156283749281029)
    amt: float = Field(..., example=85.50)
    category: str = Field(..., example="entertainment")
    lat: float = Field(..., example=40.7128)
    long: float = Field(..., example=-74.0060)
    merch_lat: float = Field(..., example=40.7250)
    merch_long: float = Field(..., example=-73.9900)
    timestamp: str = Field(None, example="2026-06-26T15:18:43.123456")

@app.post("/score")
def score_transaction(payload: TransactionRequest):
    """
    Accepts transaction swiping events, preprocesses dynamic velocity and distance features 
    using the Redis cache, and evaluates fraud risk using the pre-loaded Random Forest.
    """
    if not rf_model:
        raise HTTPException(status_code=500, detail="Classifier model is not loaded.")
        
    try:
        # 1. Category Encoding Conversion
        category_clean = payload.category.lower().strip()
        if category_clean not in label_encoder.classes_:
            category_encoded = 0
        else:
            category_encoded = int(label_encoder.transform([category_clean])[0])
            
        # 2. Compute cyclical temporal features from transaction timestamp
        if payload.timestamp:
            try:
                dt = datetime.fromisoformat(payload.timestamp)
            except ValueError:
                dt = datetime.now()
        else:
            dt = datetime.now()
            
        hour = dt.hour
        day_of_week = dt.weekday()
        hour_sin = math.sin(2 * np.pi * hour / 24.0)
        hour_cos = math.cos(2 * np.pi * hour / 24.0)
        
        # 3. Compute geographic distance
        distance_km = get_haversine_distance(payload.lat, payload.long, payload.merch_lat, payload.merch_long)
        
        # 4. Redis Caching: Increment cardholder transaction count (Velocity) with 24h expiration
        redis_key = f"user:{payload.cc_num}:velocity"
        redis_failed = False
        try:
            user_tx_count = r_client.incr(redis_key)
            # Set TTL of 24 hours (86400 seconds) if it's a new or expired counter
            if user_tx_count == 1:
                r_client.expire(redis_key, 86400)
        except Exception as redis_err:
            print(f"Warning: Redis cache unavailable. Falling back to default velocity. Error: {redis_err}")
            user_tx_count = 1
            redis_failed = True
        
        # 5. Extract spending baseline and calculate ratio deviation
        cc_str = str(payload.cc_num)
        user_avg = user_profiles.get(cc_str, user_profiles.get("GLOBAL_DEFAULT", 50.0))
        user_avg_spend_ratio = payload.amt / (user_avg + 1e-5)
        
        # 6. Score feature vector
        feature_vector = np.array([[
            payload.amt,
            category_encoded,
            hour_sin,
            hour_cos,
            day_of_week,
            distance_km,
            user_tx_count,
            user_avg_spend_ratio
        ]])
        
        fraud_probability = float(rf_model.predict_proba(feature_vector)[0, 1])
        prediction_decision = "DECLINE" if fraud_probability >= 0.5 else "APPROVE"
        
        response_data = {
            "transaction_id": payload.transaction_id,
            "fraud_probability": round(fraud_probability, 4),
            "decision": prediction_decision,
            "metrics": {
                "distance_km": round(distance_km, 2),
                "tx_velocity_count": user_tx_count,
                "spend_ratio": round(user_avg_spend_ratio, 2)
            }
        }
        if redis_failed:
            response_data["warning"] = "Redis feature store offline. Using default velocity."
            
        return response_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")

@app.get("/health")
def health_check():
    """
    Checks the status of the loaded ML artifacts and connections 
    to the Redis database cluster.
    """
    try:
        redis_connected = r_client.ping()
    except Exception:
        redis_connected = False
        
    return {
        "status": "healthy" if rf_model else "unhealthy",
        "model_loaded": rf_model is not None,
        "redis_feature_cache_connected": redis_connected
    }
