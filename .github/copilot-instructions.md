# USD Invoice Converter

- Keep invoice processing local; do not persist uploaded invoice contents.
- Use Lietuvos bankas structured exchange-rate services, not HTML scraping.
- Use Decimal for currency calculations and preserve the uploaded PDF pages.
- Run focused tests with `python -m pytest` after changing extraction, rates, or PDF generation.
