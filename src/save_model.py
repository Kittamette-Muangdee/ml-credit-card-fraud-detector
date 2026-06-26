import os
import json
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier

def train_and_save_rf():
    """
    Fits our champion model (Random Forest) under leakage-free conditions
    and serializes all trained configurations to pickle format for API serving.
    """
    print("Loading historical Sparkov transaction records...")
    df = pd.read_csv("data/sparkov_historical.csv")
    
    # 1. Feature Engineering
    df["trans_date_trans_time"] = pd.to_datetime(df["trans_date"] + " " + df["trans_time"])
    df = df.sort_values("trans_date_trans_time").reset_index(drop=True)
    
    # Compute transaction velocity frequency count grouped by credit card
    df["user_tx_count"] = df.groupby("cc_num").cumcount() + 1
    
    df["hour"] = df["trans_date_trans_time"].dt.hour
    df["day_of_week"] = df["trans_date_trans_time"].dt.dayofweek
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"]/24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"]/24.0)
    
    lat1, lon1 = np.radians(df["lat"]), np.radians(df["long"])
    lat2, lon2 = np.radians(df["merch_lat"]), np.radians(df["merch_long"])
    a = np.sin((lat2-lat1)/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2-lon1)/2)**2
    df["distance_km"] = 6371.0 * 2 * np.arcsin(np.sqrt(a))
    
    le = LabelEncoder()
    df["category_encoded"] = le.fit_transform(df["category"])
    
    # Export LabelEncoder so real-time microservices can decode live categories
    os.makedirs("models", exist_ok=True)
    joblib.dump(le, "models/label_encoder.pkl")
    
    # 2. Chronological-safe train/test split to prevent leakage
    train_df, test_df = train_test_split(df, test_size=0.2, random_state=42, stratify=df["is_fraud"])
    
    # Compute cardholder historical averages ONLY using training data
    user_avg = train_df.groupby("cc_num")["amt"].mean().to_dict()
    global_mean = train_df["amt"].mean()
    
    train_df["user_avg_spend"] = train_df["cc_num"].map(user_avg).fillna(global_mean)
    test_df["user_avg_spend"] = test_df["cc_num"].map(user_avg).fillna(global_mean)
    
    train_df["user_avg_spend_ratio"] = train_df["amt"] / (train_df["user_avg_spend"] + 1e-5)
    test_df["user_avg_spend_ratio"] = test_df["amt"] / (test_df["user_avg_spend"] + 1e-5)
    
    # Convert cc_num keys to strings for JSON mapping compatibility
    serialized_profiles = {str(k): float(v) for k, v in user_avg.items()}
    serialized_profiles["GLOBAL_DEFAULT"] = float(global_mean)
    
    with open("models/user_profiles.json", "w") as f:
        json.dump(serialized_profiles, f, indent=4)
    print("Saved user profile spend statistics maps.")
    
    # 3. Train champion classifier (Random Forest)
    features = ["amt", "category_encoded", "hour_sin", "hour_cos", "day_of_week", "distance_km", "user_tx_count", "user_avg_spend_ratio"]
    X_train, y_train = train_df[features], train_df["is_fraud"]
    
    print("Training Random Forest Classifier model...")
    rf_model = RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=42, n_jobs=-1)
    rf_model.fit(X_train, y_train)
    
    joblib.dump(rf_model, "models/random_forest_model.pkl")
    print("Successfully trained and saved Random Forest classifier to models/random_forest_model.pkl!")

if __name__ == "__main__":
    train_and_save_rf()
