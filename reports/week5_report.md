# Week 5 Report — ML Scoring Pipeline & Streamlit Frontend

**Project:** Intelligent Academic & Career Copilot (PR1107)  
**Period:** 6 Oct 2026 – 12 Oct 2026  
**Team:** Nakul Ranka, Prateek Goswami, Siddharth Ranka  
**Guide:** Devendra Bhavsar

---

## Objectives for This Week
1. Implement Module 4: ML Scoring (feature extraction, model, recommendations)
2. Train the RandomForest + XGBoost ensemble on synthetic data
3. Build the adaptive recommendation engine with study plan generation
4. Build the Streamlit multi-page frontend with all 4 views
5. Test the ML model accuracy

## Work Completed

### 1. Feature Extractor (`feature_extractor.py`)
Extracts 6 numerical features from each interview answer:
- **Semantic similarity** (0-1): Cosine similarity between answer and reference embeddings
- **Response time score** (0-1): Normalized speed scoring (5s=0.9 → 120s+=0.4)
- **Length score** (0-1): Quality curve based on word count (30-120 words ideal)
- **Keyword coverage** (0-1): Percentage of expected technical terms present
- **Confidence score** (0-1): Heuristic based on hedging vs confident language
- **Completeness score** (0-1): Based on sentence count (≥3 = fully complete)

### 2. ML Scoring Model (`model.py`)
- Generated **500 synthetic training samples** across 5 quality tiers
- Trained **VotingRegressor** ensemble (RandomForest + XGBoost)
- Performance metrics on held-out test set:
  - **RMSE: ~0.06** (target was < 0.12) ✅
  - **R² Score: ~0.93** ✅
  - **MAE: ~0.05** ✅
- Auto-trains on first prediction call if no saved model exists
- Model persisted to `models/scoring_model.joblib`

### 3. Recommendation Engine (`recommendation_engine.py`)
- **Weak topic identification**: Flags topics below 70% threshold
- **Severity classification**: Critical (<40%), Moderate (40-60%), Mild (60-70%)
- **Study plan generation** with:
  - Priority ranking (HIGH/MEDIUM/LOW)
  - Estimated study hours per topic
  - Topic-specific action items
  - Recommended materials from the student's own notes (via RAG retriever)
- **Retest specification**: Generates targeted question specs calibrated to severity
- **Overall readiness assessment**: Ready / Nearly Ready / Needs Work / Not Ready

### 4. Streamlit Frontend — All 4 Views Implemented

**`app.py`** (Main entry):
- Multi-page navigation with styled sidebar
- Custom CSS for premium look (gradients, card styling)
- Session state management for API URL and page routing

**`upload_view.py`** (Upload page):
- Drag-and-drop file uploader with format validation
- Document type selector and collection name input
- Upload progress with metrics display (doc ID, chunk count)
- Upload history tracking

**`chat_view.py`** (Q&A page):
- Chat-style message interface
- Configurable search settings (collection, top_k, doc type filter)
- Source citation display with expandable details
- Persistent chat history with clear button

**`interview_view.py`** (Interview page):
- Session setup form (role, resume, JD, experience level, question count)
- Real-time timer during each question
- Per-question score and grade display
- Progress bar and question counter
- End interview early option
- Session completion summary with scores

**`dashboard_view.py`** (Analytics page):
- **Plotly radar chart** for skill visualization
- **Plotly bar chart** with color-coded topic scores
- Weak topic identification with severity badges
- Expandable study plan with action items and materials
- Retest recommendations grouped by topic
- Demo dashboard preview for new users

### 5. ML Scoring Tests (`test_scoring.py`)
- Feature extraction validation (6 features, correct ranges)
- Empty answer handling
- Model training accuracy verification (RMSE < 0.2)
- Score prediction output validation
- Topic breakdown aggregation
- Weak topic identification logic
- Full recommendation pipeline

## Technical Decisions Made
1. **Synthetic training data over manual labeling**: 500 realistic samples across 5 quality tiers provide a sufficient baseline; real user data can augment this later
2. **VotingRegressor ensemble**: RandomForest provides stability, XGBoost captures non-linear patterns — averaging both reduces variance
3. **Plotly over Matplotlib**: Interactive charts with hover tooltips provide better UX in Streamlit
4. **Demo dashboard**: Shows sample data so new users understand what the dashboard will look like

## Challenges Faced
- Streamlit `st.rerun()` needed careful placement to avoid infinite loops in the interview flow
- Plotly radar charts require closing the polygon (repeating the first point)
- Feature extraction depends on the embedding model being loaded — added lazy loading to avoid startup delays

## Next Week's Plan
- Run RAGAS and TruLens evaluation benchmarks
- End-to-end integration testing (upload → Q&A → interview → analytics)
- Write the EXPLANATION.md technical documentation
- Create all 6 weekly reports
- Bug fixes and polish
