import time
import random
import requests
from generator import TransactionSimulator

API_URL = "http://127.0.0.1:8000/score"

def run_live_demonstration():
    """
    Simulates a live credit card transaction stream client, feeding generated
    events directly into our FastAPI server while catching connection failures.
    """
    print("Initializing real-time credit card transaction stream generator...")
    # Initialize simulator
    simulator = TransactionSimulator(num_users=20, num_merchants=5, fraud_rate=0.15)
    
    print(f"Connecting to FastAPI model scoring microservice at: {API_URL}")
    print("Checking endpoint health...")
    try:
        health_resp = requests.get("http://127.0.0.1:8000/health")
        if health_resp.status_code == 200:
            print("API is healthy. Starting live transaction stream. Press Ctrl+C to terminate demonstration.\n")
        else:
            print(f"API returned unhealthy status: {health_resp.json()}")
            return
    except requests.exceptions.ConnectionError:
        print("Error: FastAPI server is not running. Please start uvicorn first on port 8000!")
        return

    try:
        tx_index = 1
        while True:
            # Generate a transaction event
            tx = simulator.generate_transaction()
            
            print(f"[Tx #{tx_index}] Cardholder cc_num: {tx['user_id']} swiped ${tx['amount']} at merchant {tx['merchant_id']} ({tx['category']})")
            
            # Map simulator attributes to payload schema
            payload = {
                "transaction_id": tx["transaction_id"],
                "cc_num": int(tx["user_id"].replace("usr_", "")),
                "amt": tx["amount"],
                "category": tx["category"],
                "lat": tx["tx_lat"],
                "long": tx["tx_lon"],
                "merch_lat": tx["tx_lat"] - 0.01,
                "merch_long": tx["tx_lon"] + 0.01,
                "timestamp": tx["timestamp"]
            }
            
            # Inject geographic anomaly coordinates for fraud patterns
            if tx["is_fraud"] == 1:
                # Fraud swiped thousands of kilometers away
                payload["merch_lat"] = tx["tx_lat"] + random.uniform(30, 80)
                payload["merch_long"] = tx["tx_lon"] + random.uniform(30, 80)
                print("   [WARNING] INJECTING FRAUD PATTERN (Large transaction amount/distant location!)")

            # Post payload with connection loss resilience
            try:
                response = requests.post(API_URL, json=payload, timeout=5)
                if response.status_code == 200:
                    result = response.json()
                    decision = result["decision"]
                    prob = result["fraud_probability"]
                    
                    if decision == "DECLINE":
                        print(f"   [DECLINE] DECISION: {decision} (Fraud Probability: {prob:.4f})")
                        print(f"      [Alert Reason] Distance: {result['metrics']['distance_km']}km, Spend Deviation Ratio: {result['metrics']['spend_ratio']}x\n")
                    else:
                        print(f"   [APPROVE] DECISION: {decision} (Fraud Probability: {prob:.4f})\n")
                else:
                    print(f"   [ERROR] Prediction service returned error: {response.text}\n")
            except requests.exceptions.RequestException as req_err:
                print(f"   [CONNECTION LOSS] Failed to connect to server: {req_err}\n")
                
            tx_index += 1
            # Wait between swipes
            time.sleep(random.uniform(1.0, 2.5))
            
    except KeyboardInterrupt:
        print("\nDemonstration terminated. All transaction events stopped.")

if __name__ == "__main__":
    run_live_demonstration()
