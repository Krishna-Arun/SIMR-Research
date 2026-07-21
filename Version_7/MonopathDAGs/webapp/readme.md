# DynamicData Web Application

This FastAPI-based web server provides a frontend for:

- Logging in as a user
- Evaluating patient timeline graphs
- Reviewing and scoring synthetic case reports
- Visualizing dynamic DAGs built from clinical narratives

---

##  Quick Start

### 1. Install dependencies

From the project root:

```
pip install -r requirements.txt
```

Make sure you have the `.env` file loaded with API keys used for synthetic generation and LLM interaction.

---

### 2. Run the FastAPI Server

From the `webapp/` directory:

```
uvicorn main:app --reload
```

Then open:

```
http://localhost:8000/
```

This will:
- Load login.html if no user cookie is found
- Redirect to `/node-evaluation`, `/synthetic-evaluation`, or `/graph-visualization` based on routes

---

## 📂 Folder Structure

```
webapp/
├── static/                      # Static HTML/CSS/JS and graphs
│   ├── index.html               # Home after login
│   ├── login.html               # Login page
│   ├── node-evaluation.html     # Node/edge evaluation UI
│   ├── synthetic-evaluation.html# Synthetic case eval UI
│   ├── graph-visualization.html# Graph browser
│   ├── graphs/                  # JSON graph files
│   ├── synthetic_outputs/       # Generated synthetic narratives
│   └── user_data/               # Per-user evaluation tracking
├── .data/localdata.db           # SQLite DB (auto-created)
├── main.py                      # FastAPI backend app
```

---

## Features

###  User Login

- POST `/api/login`: creates user if not present
- Sets cookies: `user_id`, `user_name`

###  Node Evaluation

- GET `/node-evaluation`: Loads graph node/edge feedback page
- POST `/api/submit-batch-eval`: Saves accuracy annotations for each element

###  Synthetic Case Evaluation

- GET `/synthetic-evaluation`: Loads synthetic evaluation UI
- GET `/api/get-synthetic-reports`: Returns sample cases
- POST `/api/submit-synthetic-evals`: Saves Likert ratings (Q1–Q5)

###  Graph Viewer

- GET `/graph-visualization`: Loads DAG viewer page
- GET `/graph-data`: Static graph object
- POST `/graph-data`: Update client-side graph structure

---

## 🧾API Summary

| Endpoint                         | Method | Description                        |
|----------------------------------|--------|------------------------------------|
| `/`                              | GET    | Login or redirect to index         |
| `/api/login`                     | POST   | Create/login user                  |
| `/api/user-data`                | GET    | Returns username/id from cookie   |
| `/api/get-graph-data`           | GET    | Returns static test graph          |
| `/api/submit-batch-eval`        | POST   | Submit graph element evaluations   |
| `/api/submit-synthetic-evals`   | POST   | Submit synthetic case evaluations  |
| `/logout`                        | GET    | Deletes session cookie             |

---

##  Database Tables

- `users`: Registered usernames
- `evaluations`: Node/edge-level accuracy judgments
- `synthetic_cases`: Likert-scale feedback on synthetic narratives

SQLite DB is auto-initialized in `webapp/.data/localdata.db`.

---

## License

Licensed under the Apache License 2.0. See the `LICENSE` file in the project root.
