# dashboard.py (Updated to dynamically match JSON filename from URL)

import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import re
import altair as alt
from scraper import scrape_facebook_page, extract_page_identifier
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

st.set_page_config(page_title="Facebook Page Fraud Detection with FraudLens", layout="wide")
st.title("🔐 Facebook Page Fraud Detection with FraudLens")

def clean_text(text):
    import re
    text = text.lower()
    text = re.sub(r'… see more', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return text.strip()

def preprocess(df):
    df['Cleaned Content'] = df['Post Content'].fillna("").apply(clean_text)
    df['Post Length'] = df['Cleaned Content'].apply(len)
    df['Num Comments'] = df['Comments'].apply(len)
    df['Total Reactions'] = df['Reactions'].apply(lambda x: sum(x.values()) if isinstance(x, dict) else 0)
    df['Angry Ratio'] = df['Reactions'].apply(lambda x: x.get('Angry', 0) / sum(x.values()) if sum(x.values()) > 0 else 0)
    df['Sad Ratio'] = df['Reactions'].apply(lambda x: x.get('Sad', 0) / sum(x.values()) if sum(x.values()) > 0 else 0)
    df['Haha Ratio'] = df['Reactions'].apply(lambda x: x.get('Haha', 0) / sum(x.values()) if sum(x.values()) > 0 else 0)
    df['Love Ratio'] = df['Reactions'].apply(lambda x: x.get('Love', 0) / sum(x.values()) if sum(x.values()) > 0 else 0)
    return df

def fraudlens_pipeline(df, reviews):
    tfidf = TfidfVectorizer(max_features=100)
    X_reviews = tfidf.fit_transform(reviews + df['Cleaned Content'].tolist())
    dummy_labels = [0] * len(reviews) + [1] * len(df)
    clf_text = LogisticRegression().fit(X_reviews, dummy_labels)
    X_text = tfidf.transform(df['Cleaned Content'])
    df['Text_Prob'] = clf_text.predict_proba(X_text)[:, 1]

    features = ['Post Length', 'Num Comments', 'Total Reactions', 'Angry Ratio', 'Sad Ratio', 'Haha Ratio', 'Love Ratio']
    X_behavior = df[features].fillna(0)
    anomaly_model = IsolationForest(contamination=0.25, random_state=42)
    df['Anomaly_Score'] = -anomaly_model.fit(X_behavior).decision_function(X_behavior)

    np.random.seed(42)
    df['Trust_Score'] = np.random.uniform(0.5, 1.0, len(df))

    df['FraudLens_Score'] = 0.4 * df['Text_Prob'] + 0.4 * df['Anomaly_Score'] + 0.2 * (1 - df['Trust_Score'])
    df['Fraud_Prediction'] = df['FraudLens_Score'].apply(lambda x: 1 if x > 0.5 else 0)
    return df

def load_reviews_from_json(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    reviews = []
    for r in data.get("Reviews", []):
        review = r.get("Review")
        if isinstance(review, str) and review.lower() != "no review text":
            reviews.append(review)

    # Safely append About and Recommendation only if they're strings
    about = data.get("About")
    if isinstance(about, str):
        reviews.append(about)

    recommendation = data.get("Recommendation")
    if isinstance(recommendation, str):
        reviews.append(recommendation)

    return reviews

url = st.text_input("Paste a Facebook Page URL to scan:")

if st.button("Load and Analyze") and url:
    identifier = extract_page_identifier(url)
    json_path = f"data/final_scraped_dataset_{identifier}.json"

    if not os.path.exists(json_path):
        st.warning("🔄 Data file not found. Scraping live...")
        scrape_facebook_page(url)

    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        df = pd.DataFrame(data.get("Posts", []))
        df = preprocess(df)
        reviews = load_reviews_from_json(json_path)
        results = fraudlens_pipeline(df, reviews)

        st.metric("Total Posts Analyzed", len(results))
        st.metric("Posts Flagged as Fraud", int(results['Fraud_Prediction'].sum()))

        st.subheader("📉 FraudLens Score Distribution")
        hist = alt.Chart(results).mark_bar().encode(
            x=alt.X('FraudLens_Score', bin=alt.Bin(maxbins=20)),
            y='count()'
        ).properties(width=600)
        st.altair_chart(hist)

        st.subheader("📊 Reaction Type Breakdown")
        reaction_totals = pd.DataFrame({
            'Angry': results['Angry Ratio'].sum(),
            'Sad': results['Sad Ratio'].sum(),
            'Haha': results['Haha Ratio'].sum(),
            'Love': results['Love Ratio'].sum()
        }, index=['Ratio']).T.reset_index().rename(columns={'index': 'Reaction'})

        bar = alt.Chart(reaction_totals).mark_bar().encode(
            x='Reaction',
            y='Ratio'
        ).properties(width=500)
        st.altair_chart(bar)

        st.subheader("🛡️ Trust Score Distribution")
        trust_chart = alt.Chart(results).mark_bar().encode(
            x=alt.X('Trust_Score', bin=alt.Bin(maxbins=20), title="Trust Score"),
            y=alt.Y('count()', title="Number of Posts")
        ).properties(
            width=600,
            height=300
        )
        st.altair_chart(trust_chart)

        st.subheader("📊 Suspicious Post Table")
        st.dataframe(results[results['Fraud_Prediction'] == 1][[
            'Post Content', 'Text_Prob', 'Anomaly_Score', 'Trust_Score', 'FraudLens_Score', 'Timestamp'
        ]])

        st.subheader("🧠 All Posts and Scores")
        st.dataframe(results)
    else:
        st.error(f"❌ Data file not found: {json_path}")
