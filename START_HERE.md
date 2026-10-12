# Run Supplier Delivery Assurance locally

This package contains the complete application: a Python HTTP server, SQLite persistence, a vanilla HTML/CSS/JavaScript interface, the Python Monte Carlo engine, synthetic data, original msg branding, documentation and tests. No frontend build, Node installation, API key or cloud account is needed to run it.

## 1. Open in VS Code

Extract the ZIP. In VS Code, select **File → Open Folder** and open the extracted `supplier-delivery-assurance` folder containing `app.py`. Open **Terminal → New Terminal**. Use Python 3.11 or newer; this package was tested with Python 3.12.14.

## 2. Create the environment and start the app

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

These commands invoke the virtual environment's Python directly; activation is unnecessary. NumPy and SciPy are required for Economic impact. The delivery worklist and persistence use Python's standard library. Dependency installation needs internet access; the local application works offline after installation.

## 3. Open the HTML interface

Open **http://127.0.0.1:8000/index.html** in your browser. **http://localhost:8000/index.html** and the root URL also work when localhost resolves to IPv4.

The actual HTML file is `dist/index.html`. Python serves this file and its CSS/JavaScript assets, saves workspace changes, and runs simulations. Keep the terminal running. Double-clicking the HTML file or using VS Code Live Server does not provide the Python API or SQLite persistence.

Press **Ctrl+C** in the terminal to stop. To restart later, run the last command for your operating system again; no reinstall is needed. If port 8000 is occupied, append `--port 8001` and open the corresponding URL.

In VS Code, use **Python: Select Interpreter → Enter interpreter path → Find** to select `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on macOS/Linux if the environment is not listed.

## Where to edit

| File | Purpose |
| --- | --- |
| `app.py` | Python server, API, SQLite persistence and source download |
| `dist/index.html` | HTML application shell |
| `dist/styles.css` | Layout, responsive styles and msg palette |
| `dist/app.js` | Screens and interactions, rendered into the HTML shell |
| `dist/engine.mjs` | Delivery rules, extraction and matching in plain JavaScript |
| `dist/economics.js` | Economic-impact screen and Python API calls |
| `dist/monte_carlo.py`, `dist/mc_core.py` | Python simulation and statistical calculations |
| `dist/msg-logo.svg`, `dist/icon.svg` | Brand assets |
| `seed.py`, `dist/seed.json` | Synthetic scenario generator and data |
| `dist/economic-example.json` | Example simulation configuration |
| `dist/mc-worker.js` | Browser-only Python fallback retained from the hosted app; unused with the local Python backend |
| `README.md`, `MONTE_CARLO.md` | Workflow, architecture, assumptions and model documentation |

Refresh the browser after HTML/CSS/JavaScript changes. Restart the server after Python changes. `dist` contains editable source files; it is not a compiled bundle.

## Persistence and scope

The server creates `.runtime/assurance.sqlite3` on first start. This stores the workspace and revisions. Keep that file to retain your work; it is not included in this clean package. JSON export/import is available in the app. The demonstration starts with a fixed scenario date and synthetic suppliers.

This is a single-user demonstration with rule-based message extraction and a separate Monte Carlo model. It contains no connected LLM, SAP integration or live email sending. The hosted site is unchanged by this local download.

## Verification

Using the same virtual environment's Python:

```bash
python -m unittest -v test_server.py test_monte_carlo.py
```

Replace `python` with `.venv/bin/python` or `.\.venv\Scripts\python.exe` if the environment is not activated. The tests cover HTTP delivery of HTML and logo assets, persistence, save conflicts, simulation API responses, source packaging and numerical behavior. Optional delivery-rule tests require Node 22+:

```bash
node test_engine.mjs
```

The downloadable package has been checked at the source, HTTP/API and model levels. Full browser interaction and visual testing were not available in the packaging environment.
