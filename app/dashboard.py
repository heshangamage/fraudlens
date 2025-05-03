# dashboard.py (Updated to use trained models)
import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import re
import altair as alt
import joblib

from scraper import scrape_facebook_page, extract_page_identifier
from sentence_transformers import SentenceTransformer

# Load pretrained models
sbert_model = SentenceTransformer("./fine_tuned_sbert_fraudlens/")
tfidf = joblib.load("tfidf_vectorizer.pkl")
sbert_clf = joblib.load("logistic_model_sbert.pkl")
anomaly_model = joblib.load("isolation_model.pkl")

st.set_page_config(page_title="Facebook Page Fraud Detection with FraudLens", layout="wide")
st.title("🔐 Facebook Page Fraud Detection with FraudLens")

def clean_text(text):
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

def fraudlens_pipeline(df):
    # SBERT embedding
    sbert_embeddings = sbert_model.encode(df['Cleaned Content'].tolist(), show_progress_bar=False)
    sbert_df = pd.DataFrame(sbert_embeddings, columns=[f'sbert_{i}' for i in range(sbert_embeddings.shape[1])])
    df = pd.concat([df.reset_index(drop=True), sbert_df.reset_index(drop=True)], axis=1)

    # Predict SBERT_Prob
    df['SBERT_Prob'] = sbert_clf.predict_proba(sbert_df)[:, 1]

    # Anomaly score
    features = ['Post Length', 'Num Comments', 'Total Reactions', 'Angry Ratio', 'Sad Ratio', 'Haha Ratio', 'Love Ratio']
    X_behavior = df[features].fillna(0)
    df['Anomaly_Score'] = -anomaly_model.decision_function(X_behavior)

    # Trust score
    df['Trust_Score'] = (
        0.6 * df['Love Ratio'] + 
        0.2 * df['Haha Ratio'] + 
        0.1 * (df['Post Length'] / df['Post Length'].max()) + 
        0.1 * (1 - df['Angry Ratio'])
    ).clip(0.4, 1.0)

    # Final score and prediction
    df['FraudLens_Score'] = 0.4 * df['SBERT_Prob'] + 0.4 * df['Anomaly_Score'] + 0.2 * (1 - df['Trust_Score'])
    df['Fraud_Prediction'] = df['FraudLens_Score'].apply(lambda x: 1 if x > 0.3 else 0)
    return df

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
        results = fraudlens_pipeline(df)

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
        ).properties(width=600, height=300)
        st.altair_chart(trust_chart)

        st.subheader("📊 Suspicious Post Table")
        st.dataframe(results[results['Fraud_Prediction'] == 1][[
            'Post Content', 'SBERT_Prob', 'Anomaly_Score', 'Trust_Score', 'FraudLens_Score'
        ]])

        st.subheader("🧠 All Posts and Scores")
        st.dataframe(results)
    else:
        st.error(f"❌ Data file not found: {json_path}")
