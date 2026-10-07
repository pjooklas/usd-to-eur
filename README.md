# USD Invoice Converter

A local web app that reads a selectable-text USD invoice, fetches the historical USD/EUR rate published by Lietuvos bankas, and adds the rate and converted EUR total below the invoice's USD total. If no safe placement can be found, a conversion summary page is appended instead.

## Run locally

```bash
~/.local/bin/uv venv --python 3.12 .venv
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python app.py
```

Open `http://127.0.0.1:5000`. Upload a PDF, review or correct the detected issue date and USD total, then confirm to prepare and download the converted PDF. Scanned/image-only PDFs are not supported in this version.

Invoice bytes are handled in the local app process and are not stored by the application. Exchange rates are requested from Lietuvos bankas' official web service. The app uses the most recent published USD rate on or before the issue date and prints the rate date and source in the output PDF. The calculation is `EUR = USD / USD-per-EUR`, rounded to cents with half-up rounding.

The app binds to localhost only and limits uploads to 20 MB.

## Tests

```bash
python -m pytest
```
