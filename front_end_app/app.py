import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dateutil import parser
import re
from flask import Flask, render_template, request, abort
from werkzeug.utils import secure_filename
import google.generativeai as genai
from google.generativeai import GenerationConfig
from dotenv import load_dotenv

from ocr_pipeline import (
    batch_convert_pdfs_to_images,
    ocr_financial_document,
    verify_financial_extraction,
    enrich_with_other_options
)

# ── Load API Key ────────────────────────────────────────────────
load_dotenv()
api_key = os.getenv("GENAI_API_KEY", "AIzaSyC90nXGzSxx1MlzM4TBgFtwdA8EhQo_oU4")
genai.configure(api_key=api_key)
model = genai.GenerativeModel(
    'gemini-2.5-pro',
    generation_config=GenerationConfig(temperature=1.8)
)

# ── Flask App Setup ────────────────────────────────────────────
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
UPLOAD_FOLDER     = 'uploads'
IMAGES_FOLDER     = 'images'

app = Flask(__name__)
app.config['UPLOAD_FOLDER']  = UPLOAD_FOLDER
app.config['IMAGES_FOLDER']  = IMAGES_FOLDER
BATCH_LIMIT                = int(app.config.get('BATCH_LIMIT', 50))

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGES_FOLDER, exist_ok=True)

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ── Routes ──────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def upload_files():
    if request.method == 'POST':
        # 1) Ensure files are present
        if 'files' not in request.files:
            abort(400, 'No files part')
        upload_list = request.files.getlist('files')
        if not upload_list:
            abort(400, 'No files selected')

        # 2) Save uploads
        files = []
        for file in upload_list:
            if file and allowed_file(file.filename):
                fn   = secure_filename(file.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
                file.save(path)
                files.append(path)

        if not files:
            return render_template('upload.html', error="No valid invoice files uploaded.")

        # 3) Separate PDFs vs. image files
        pdf_paths   = [f for f in files if f.lower().endswith('.pdf')]
        image_paths = [f for f in files if not f.lower().endswith('.pdf')]

        # 4) Convert PDFs to images
        if pdf_paths:
            converted = batch_convert_pdfs_to_images(pdf_paths, app.config['IMAGES_FOLDER'])
            image_paths.extend(converted)

        # 5) Batch OCR → verify → enrich
        batches      = [image_paths[i:i+BATCH_LIMIT] for i in range(0, len(image_paths), BATCH_LIMIT)]
        all_verified = []

        for batch in batches:
            extracted = ocr_financial_document(model, batch)
            verified  = verify_financial_extraction(model, batch, extracted)
            enriched  = enrich_with_other_options(verified)
            all_verified.extend(enriched)
            time.sleep(4)  # throttle to respect rate limits

        # 6) Post-process fields
        for inv in all_verified:
            if 'buyer_name' in inv and isinstance(inv['buyer_name'], str):
                inv['buyer_name'] = inv['buyer_name'].title()
            if 'supplier_name' in inv and isinstance(inv['supplier_name'], str):
                inv['supplier_name'] = inv['supplier_name'].title()
            if 'invoice_date' in inv:
                try:
                    dt = parser.parse(inv['invoice_date'], dayfirst=True)
                    inv['invoice_date'] = dt.strftime('%Y-%m-%d')
                except:
                    pass
            if 'total_invoice_amount' in inv:
                try:
                    amt = float(re.sub(r'[^\d.]', '', str(inv['total_invoice_amount'])))
                    inv['total_invoice_amount'] = f"{amt:,.2f}"
                except:
                    pass

        # 7) Render the results
        return render_template('results.html', invoices=all_verified)

    # GET → show upload form
    return render_template('upload.html')


# ── Run App ────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
