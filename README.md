# USD Invoice Converter

A local web app that reads a selectable-text USD invoice, fetches the historical USD/EUR rate published by Lietuvos bankas, and adds the rate and converted EUR total below the invoice's USD total. If no safe placement can be found, a conversion summary page is appended instead.

## Run locally

```bash
~/.local/bin/uv venv --python 3.12 .venv
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python app.py
```

Open `http://127.0.0.1:5000`. Upload a PDF, review or correct the detected issue date and USD total, then confirm to prepare and download the converted PDF. Scanned/image-only PDFs are not supported in this version.

Invoice bytes are handled in the app process and are not saved to application files or a database. The request upload stream is closed after reading, and the browser releases its reference to the original PDF after conversion. The converted PDF remains in browser memory until it is downloaded or the page is reset/closed. A hosted deployment receives the original PDF for processing. Exchange rates are requested from Lietuvos bankas' official web service. The app uses the most recent published USD rate on or before the issue date and prints the rate date and source in the output PDF. The calculation is `EUR = USD / USD-per-EUR`, rounded to cents with half-up rounding.

The app binds to localhost only and limits uploads to 20 MB.

## Deploy on Render

Create one Render Web Service connected to this GitHub repository. The Flask backend serves the HTML page and its CSS/JavaScript, so the frontend and backend deploy together; no separate frontend service is needed.

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`

The app does not save uploaded PDFs, but a hosted deployment receives their contents for processing. Add authentication before sharing the public service URL or using it with sensitive invoices.

## Tests

```bash
python -m pytest
```
