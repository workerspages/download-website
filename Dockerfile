FROM mcr.microsoft.com/playwright/python:v1.57.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY download_site.py .
COPY download_site_playwright.py .

CMD ["python", "download_site_playwright.py"]
