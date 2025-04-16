
import json
import pandas as pd
import numpy as np
import re
import sys
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import IsolationForest
import joblib

# --- Utility functions ---
def clean_text(text):
    text = text.lower()
    text = re.sub(r'… see more', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return text.strip()

def preprocess(df):
    df['About Cleaned'] = df['About'].fillna("").apply(clean_text)
    df['Recommendation Sentiment'] = df['Recommendation'].fillna("").apply(lambda x: 1 if "recommend" in x.lower() else 0)
    df['Cleaned Content'] = df['Post Content'].fillna("").apply(clean_text)
    df['Post Length'] = df['Cleaned Content'].apply(len)
    df['Num Comments'] = df['Comments'].apply(len)
    df['Total Reactions'] = df['Reactions'].apply(lambda x: sum(x.values()) if isinstance(x, dict) else 0)
    df['Angry Ratio'] = df['Reactions'].apply(lambda x: x.get('Angry', 0) / sum(x.values()) if sum(x.values()) > 0 else 0)
    df['Sad Ratio'] = df['Reactions'].apply(lambda x: x.get('Sad', 0) / sum(x.values()) if sum(x.values()) > 0 else 0)
    df['Haha Ratio'] = df['Reactions'].apply(lambda x: x.get('Haha', 0) / sum(x.values()) if sum(x.values()) > 0 else 0)
    df['Love Ratio'] = df['Reactions'].apply(lambda x: x.get('Love', 0) / sum(x.values()) if sum(x.values()) > 0 else 0)
    return df

# --- Load and preprocess test page dataset ---
if len(sys.argv) < 2:
    print("❌ Usage: python fraudlens_predict_new_page.py <final_scraped_dataset_page.json>")
    sys.exit(1)

input_file = sys.argv[1]
with open(input_file, "r", encoding="utf-8") as f:
    data = json.load(f)

df = pd.DataFrame(data["Posts"])
df["About"] = data.get("About", "")
df["Recommendation"] = data.get("Recommendation", "")
df["Reviews"] = [data.get("Reviews", [])] * len(df)

df = preprocess(df)

# --- Vectorize using new review + test page content ---
reviews = [r["Review"] for r in data.get("Reviews", []) if r.get("Review") and r["Review"].strip().lower() != "no review text"]
tfidf = TfidfVectorizer(max_features=100)
X_reviews = tfidf.fit_transform(reviews + df["Cleaned Content"].tolist())
dummy_labels = [0] * len(reviews) + [1] * len(df)
clf = LogisticRegression().fit(X_reviews, dummy_labels)

df["Text_Prob"] = clf.predict_proba(tfidf.transform(df["Cleaned Content"]))[:, 1]

# --- Anomaly scoring ---
features = ['Post Length', 'Num Comments', 'Total Reactions', 'Angry Ratio', 'Sad Ratio', 'Haha Ratio', 'Love Ratio', 'Recommendation Sentiment']
X_behavior = df[features].fillna(0)
anomaly_model = IsolationForest(contamination=0.25, random_state=42)
df['Anomaly_Score'] = -anomaly_model.fit(X_behavior).decision_function(X_behavior)

# --- Simulated Trust and FraudLens score ---
np.random.seed(42)
df['Trust_Score'] = np.random.uniform(0.5, 1.0, len(df))
df['FraudLens_Score'] = (
    0.35 * df['Text_Prob'] +
    0.35 * df['Anomaly_Score'] +
    0.2 * (1 - df['Trust_Score']) +
    0.1 * df['Recommendation Sentiment']
)
df['Fraud_Prediction'] = df['FraudLens_Score'].apply(lambda x: 1 if x > 0.5 else 0)

# --- Output ---
output_file = input_file.replace(".json", "_predictions.csv")
df.to_csv(output_file, index=False)
print(f"✅ Predictions saved to {output_file}")
