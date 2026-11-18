# Smart Stock AI — Python demo

This folder contains the Python/FastAPI version of Smart Stock AI. The browser app is static HTML/CSS/JavaScript; FastAPI serves the pages and the API. It uses the included MySQL demo database.

## Quick start

1. Start MySQL in XAMPP. Apache is not needed.
2. Import database/groupmate_clean_setup.sql into phpMyAdmin on a fresh demo database.
3. Import 1st prog/backend/migrations/001_ssai_demo_extension.sql into inventory_group_demo.
4. Open 1st prog/backend, copy .env.example to .env, and adjust DATABASE_URL if needed.
5. Install Python dependencies and start Uvicorn:

   Windows PowerShell:

       cd "1st prog/backend"
       python -m venv .venv
       .venv\Scripts\Activate.ps1
       Copy-Item .env.example .env
       python -m pip install -r requirements.txt
       python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

6. Open http://127.0.0.1:8000/ and register. The first account for a store is assigned the owner role.
7. Open http://127.0.0.1:8000/docs for the API documentation.

See GROUPMATE_SETUP.md for database setup, AI options, and demo steps.

## AI behavior in the demo

- The moving-average fallback is available immediately and is labeled in the UI.
- Amazon Chronos-Bolt Small is an optional local model. Install 1st prog/backend/requirements-ai.txt, set CHRONOS_ENABLED=true in .env, then restart the app. The first startup downloads the model.
- The assistant uses only data retrieved from this store. It can use Groq, Ollama, or a local grounded response.
- Model evaluation metrics are shown only when real sales history has been evaluated and evaluation_results.csv exists. The clean demo DB contains no sales rows, so it starts with no evaluation metrics.

The provided SQL is a clean demonstration schema with geography data and a Demo Store. It does not include production users, products, or sales. Do not import it over a database containing data you need.
