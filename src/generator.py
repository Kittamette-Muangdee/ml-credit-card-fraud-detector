import argparse
import csv
import json
import math
import random
import time
from datetime import datetime, timedelta

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Computes the great-circle distance (in kilometers) between two points 
    on the Earth's surface defined by latitude and longitude coordinates.
    """
    R = 6371.0 # Earth's radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

class TransactionSimulator:
    """
    Synthesizes normal and fraudulent credit card transaction events on the fly,
    generating cardholders and merchant networks with distinct spatial spending behaviors.
    """
    def __init__(self, num_users=100, num_merchants=20, fraud_rate=0.01):
        self.num_users = num_users
        self.num_merchants = num_merchants
        self.fraud_rate = fraud_rate
        self.users = []
        self.merchants = []
        self._initialize_entities()

    def _initialize_entities(self):
        """
        Creates static, stable profiles for both users and merchants 
        to ensure temporal consistency during streaming simulations.
        """
        # Generate stable cardholder demographic boundaries
        for i in range(self.num_users):
            self.users.append({
                "user_id": f"usr_{1000 + i}",
                "home_lat": random.uniform(-90, 90),
                "home_lon": random.uniform(-180, 180),
                "avg_spend": random.uniform(10, 150),
                "risk_profile": random.choice(["low", "medium"]),
            })
        
        # Generate stable merchants classified by spending category
        categories = ["entertainment", "gas_transport", "grocery_net", "shopping_net", "travel", "food"]
        for i in range(self.num_merchants):
            self.merchants.append({
                "merchant_id": f"mer_{2000 + i}",
                "merchant_lat": random.uniform(-90, 90),
                "merchant_lon": random.uniform(-180, 180),
                "category": random.choice(categories),
            })

    def generate_transaction(self, base_time=None):
        """
        Generates a single credit card transaction event. If marked as fraud,
        it injects coordinate anomalies and inflated purchase amounts.
        """
        if not base_time:
            base_time = datetime.now()
        
        user = random.choice(self.users)
        merchant = random.choice(self.merchants)
        is_fraud = random.random() < self.fraud_rate
        
        if is_fraud:
            # Fraud behavior: Out-of-bounds spend velocity and geographic coordinates shifts
            amount = random.uniform(user["avg_spend"] * 5, user["avg_spend"] * 25)
            tx_lat = user["home_lat"] + random.uniform(30, 90) * random.choice([-1, 1])
            tx_lon = user["home_lon"] + random.uniform(30, 90) * random.choice([-1, 1])
        else:
            # Normal behavior: Swiped near customer home, following normal spending curve
            amount = abs(random.normalvariate(user["avg_spend"], user["avg_spend"] * 0.3)) + 0.01
            tx_lat = user["home_lat"] + random.uniform(-0.5, 0.5)
            tx_lon = user["home_lon"] + random.uniform(-0.5, 0.5)

        tx_lat = max(min(tx_lat, 90), -90)
        tx_lon = max(min(tx_lon, 180), -180)
        distance = haversine_distance(user["home_lat"], user["home_lon"], tx_lat, tx_lon)

        return {
            "transaction_id": f"tx_{random.randint(100000000, 999999999)}",
            "timestamp": base_time.isoformat(),
            "user_id": user["user_id"],
            "amount": round(amount, 2),
            "merchant_id": merchant["merchant_id"],
            "category": merchant["category"],
            "tx_lat": round(tx_lat, 5),
            "tx_lon": round(tx_lon, 5),
            "distance_from_home": round(distance, 2),
            "is_fraud": 1 if is_fraud else 0
        }

def main():
    parser = argparse.ArgumentParser(description="Simulate credit card transaction events.")
    parser.add_argument("--mode", choices=["batch", "stream"], default="batch", help="Output mode.")
    parser.add_argument("--count", type=int, default=5000, help="Number of records for batch mode.")
    parser.add_argument("--output", type=str, default="data/transactions.csv", help="Batch output file.")
    args = parser.parse_args()

    simulator = TransactionSimulator()

    if args.mode == "batch":
        print(f"Generating {args.count} transactions in batch mode...")
        import os
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "transaction_id", "timestamp", "user_id", "amount", 
                "merchant_id", "category", "tx_lat", "tx_lon", "distance_from_home", "is_fraud"
            ])
            writer.writeheader()
            base_time = datetime.now() - timedelta(days=30)
            
            for i in range(args.count):
                base_time += timedelta(seconds=int((30 * 24 * 3600) / args.count))
                tx = simulator.generate_transaction(base_time)
                writer.writerow(tx)
        
        print(f"Batch generation completed: {args.output}")

    elif args.mode == "stream":
        print("Starting live transaction stream. Press Ctrl+C to stop...")
        try:
            while True:
                tx = simulator.generate_transaction()
                print(json.dumps(tx))
                time.sleep(random.uniform(0.1, 1.0))
        except KeyboardInterrupt:
            print("\nStream stopped.")

if __name__ == "__main__":
    main()
