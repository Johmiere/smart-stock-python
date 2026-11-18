# Smart Stock AI Python demo — setup guide

The running system uses Python/FastAPI for the backend and static HTML/CSS/JavaScript for the frontend. You do not need PHP or Apache to run this demo. MySQL remains the database.

## 1. Prepare MySQL

1. Open XAMPP Control Panel and start MySQL.
2. Open phpMyAdmin at http://localhost/phpmyadmin/.
3. On a fresh demo install, import database/groupmate_clean_setup.sql. It creates inventory_group_demo, the location lookup data, and one Demo Store.
4. Select inventory_group_demo, open the Import tab, and import 1st prog/backend/migrations/001_ssai_demo_extension.sql.

The clean SQL drops and recreates tables. Only use it for a fresh demo database. The extension adds product details, batches, and checkout fields, and creates an unknown-expiry legacy batch for any existing aggregate stock. It does not invent expiry or received dates.

If inventory_group_demo already contains data you need, make a backup before importing anything. Do not import the clean setup file over it.

## 2. Configure the Python API

Install Python 3.11 or newer. Open a PowerShell terminal in 1st prog/backend and run:

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    Copy-Item .env.example .env
    python -m pip install -r requirements.txt

Edit .env and set DATABASE_URL for your MySQL account. The example is for the usual local XAMPP setup with username root and no password:

    DATABASE_URL=mysql+pymysql://root:@127.0.0.1:3306/inventory_group_demo?charset=utf8mb4

If MySQL has a password, add it after root: and URL-encode special characters. Change SESSION_SECRET before sharing the app. Keep .env private.

Start the server from the same backend folder:

    python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

For a one-file Windows start after MySQL and the database are ready, double-click launch_windows.bat inside 1st prog/backend. It creates .venv if needed, installs the base requirements, and starts Uvicorn.

Keep the terminal open. Visit http://127.0.0.1:8000/ for the app, http://127.0.0.1:8000/docs for API documentation, and http://127.0.0.1:8000/api/health to check the MySQL connection.

## 3. Create an account and show the inventory flow

1. Select Create account, fill in the location fields, and choose Demo Store.
2. The first account for that store becomes owner; later accounts become clerks.
3. Sign in, open Product Management, and add a product with quantity, price, barcode, and expiry date.
4. Use Stock History to confirm the initial batch and movement.
5. Open Sales Transactions. A USB barcode scanner that types into the focused input works like a keyboard. Add products to the cart and click Complete sale after checkout.
6. Open Low Stock Alerts and the Dashboard to review the expiry and reorder signals.

If a product has no expiry date, the app states that its expiry risk is unknown. An expired batch is not eligible for checkout; use a reduce-stock adjustment to write it off before replenishing.

## 4. Enable Chronos-Bolt

The quick setup uses the moving-average fallback. To enable Amazon Chronos-Bolt Small:

1. In the backend virtual environment, run python -m pip install -r requirements-ai.txt.
2. Set CHRONOS_ENABLED=true in .env and keep CHRONOS_MODEL=amazon/chronos-bolt-small.
3. Restart Uvicorn. The app loads the model once when it starts. First startup downloads the model; allow time and internet access.

If Chronos cannot load, the service logs the issue and continues with the moving-average fallback. Check the Reports & AI page for the active method. The model card documents the chronos-forecasting package, quantile forecasts, and CPU/GPU choices: https://huggingface.co/amazon/chronos-bolt-small and https://github.com/amazon-science/chronos-forecasting.

## 5. Enable the assistant provider

Without provider credentials, the assistant returns a local response based on retrieved inventory data.

- Groq: set LLM_PROVIDER=groq, GROQ_API_KEY to your key, and GROQ_MODEL to a model available to your account.
- Ollama: install and start Ollama locally, pull a small model such as qwen2.5:3b, then set LLM_PROVIDER=ollama, OLLAMA_URL=http://127.0.0.1:11434/api/chat, and OLLAMA_MODEL=qwen2.5:3b.

Never commit .env or share API keys. Groq's current Python API uses chat completions; the backend calls the compatible endpoint: https://console.groq.com/docs/text-chat.

## 6. Import historical sales and evaluation

The Reports & AI page accepts a UTF-8 CSV with headers date, barcode, qty_sold. Imported historical sales do not reduce current stock. Rows with unknown barcodes or invalid values are reported and skipped.

The supplied clean database has no historical sales, so it cannot produce Chronos evaluation results by itself. Do not present empty or invented metrics as model results. Add real item-level sales history, use the evaluation notebook/process, and place actual results in evaluation_results.csv before reporting MAE, RMSE, WAPE, or classification scores.

## Troubleshooting

- API cannot connect: make sure XAMPP MySQL is running, the database was imported, and backend/.env has the correct port, username, password, and database name.
- Missing column/table errors: import the SSAI extension migration after the clean setup SQL.
- Port 8000 is busy: stop the old process with Ctrl+C or start on another port and update the app URL.
- Model not loaded: leave CHRONOS_ENABLED=false for the demo fallback or check the terminal for the model download/import error.
- On another computer, 127.0.0.1 points to that computer. For a LAN demo, bind Uvicorn to 0.0.0.0 and use the host computer's LAN IP; do this only on a trusted network.
