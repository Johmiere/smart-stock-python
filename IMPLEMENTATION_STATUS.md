# Python migration implementation status

## Delivered demo scope

The Python demo project runs its backend through FastAPI and serves static HTML/CSS/JavaScript pages from the same origin. Its runtime has no PHP dependency.

- Account creation/login/logout with bcrypt hashes, signed local session cookies, and CSRF tokens. The first account in a store is assigned owner so the clean demo DB can be set up from the browser.
- Province, municipality, barangay, and store lookup.
- Store-scoped product management with category, unit, price, reorder data, initial quantity, and optional expiry.
- Stock-in and manual adjustment recorded against batch rows and stock movements.
- Multi-item checkout with configurable PWD/Senior demo discount and nearest-expiry-first batch consumption.
- Dashboard, sales history, stock history, low-stock alerts, and owner user list.
- Expiry-aware rules and lead-time low-stock signal. Chronos-Bolt can load once at startup when enabled; the moving-average fallback is active by default.
- Assistant retrieval from current store data, with optional Groq or Ollama provider and a local grounded response when no provider is configured.
- CSV import for historical sales using date, barcode, qty_sold. Historical imports do not modify current stock.
- Honest evaluation response: if actual results do not exist, the API reports that evaluation has not been run instead of inventing metrics.

## Not implemented in this quick demo

- Camera-based QR/barcode scan fallback.
- Product CSV import and import preview.
- The Chronos-versus-moving-average-versus-Prophet holdout evaluation notebook, paired significance tests, and evaluation_results.csv generation.
- Nightly scheduled forecast runs and persistent forecast-result caching.
- User role editing, IT Admin role, and all-store admin console.
- Full production tax/discount policy validation. SPECIAL_DISCOUNT_RATE defaults to 20% for the demo and is configurable; confirm the store's accounting rules before real sales.

## Verification performed here

- Python source passed compileall syntax checking.
- Frontend JavaScript passed Node syntax checking.
- End-to-end app startup and MySQL operations could not be run in this workspace: there is no MySQL server here, and the sandbox could not download SQLAlchemy from the package index. The supplied SQL has no products or sales, so the actual demo must be connected and populated on the user's XAMPP/MySQL setup using GROUPMATE_SETUP.md.

The original uploaded ZIP remains the source backup. The deliverable Python project is packaged separately and contains no .php files. Do not present evaluation metrics until actual item sales have been evaluated.
