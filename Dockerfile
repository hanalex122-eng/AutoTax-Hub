FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    tesseract-ocr tesseract-ocr-deu tesseract-ocr-fra \
    tesseract-ocr-spa tesseract-ocr-tur tesseract-ocr-ara \
    tesseract-ocr-chi-sim libzbar0 libgl1 libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
