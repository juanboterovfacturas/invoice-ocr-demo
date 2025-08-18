import os
import json
import re
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

from pdf2image import convert_from_path
from PIL import Image
import google.generativeai as genai
from google.generativeai import GenerativeModel

try:
    from field_manager import FieldConfigManager
except ImportError:
    # Fallback if field_manager is not available
    class FieldConfigManager:
        def get_active_fields(self, field_names=None):
            return {}
        def generate_extraction_prompt(self, field_names=None):
            return ""
        def generate_verification_prompt(self, field_names=None):
            return ""

# ── PDF → Image Conversion ───────────────────────────────────────

def batch_convert_pdfs_to_images(pdf_paths: List[str], base_output_folder: str, dpi: int = 300) -> List[str]:
    """
    Given a list of PDF file paths, convert each in parallel to images.
    Returns a flat list of all generated image paths.
    """
    def worker(pdf_path: str) -> List[str]:
        stem = Path(pdf_path).stem
        out_folder = os.path.join(base_output_folder, stem)
        return convert_pdf_to_images(pdf_path, out_folder, dpi)

    all_images: List[str] = []
    with ThreadPoolExecutor() as exe:
        for img_list in exe.map(worker, pdf_paths):
            all_images.extend(img_list)
    return all_images

def convert_pdf_to_images(pdf_path: str, output_folder: str, dpi: int = 300) -> List[str]:
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    filename = Path(pdf_path).stem
    images = convert_from_path(pdf_path, dpi=dpi)
    image_paths: List[str] = []
    for i, image in enumerate(images, start=1):
        image_name = f"{filename}_page_{i}.jpg"
        image_path = os.path.join(output_folder, image_name)
        image.save(image_path, "JPEG")
        image_paths.append(image_path)
    return image_paths

# ── OCR & JSON Extraction ────────────────────────────────────────

def ocr_with_gemini(model, image_paths: List[str], instruction: str) -> str:
    """Process images with Gemini for OCR"""
    images = [Image.open(p) for p in image_paths]
    prompt = f"""
    {instruction}
    
    Analyze the provided invoice image(s) and extract the required information accurately.
    """
    response = model.generate_content([prompt, *images])
    return response.text

def extract_json(raw_text: str) -> List[Dict[str, Any]]:
    """
    Extract the first JSON array or object from raw_text (with or without ```json fences```).
    Returns a Python list of dicts.
    """
    fence_pattern = r'```json\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```'
    m = re.search(fence_pattern, raw_text, flags=re.DOTALL)
    payload = m.group(1) if m else raw_text.strip()

    if payload.lstrip().startswith('{'):
        payload = f'[{payload}]'

    try:
        data = json.loads(payload)
        if not isinstance(data, list):
            data = [data] if isinstance(data, dict) else []
        return data
    except json.JSONDecodeError:
        print(f"Failed to parse JSON: {payload[:200]}...")
        return []

def is_invoice(model, image_path: str) -> bool:
    """
    Check if the image is an invoice by running OCR and checking for specific keywords.
    """
    instruction = "Is this image an invoice? Answer with 'yes' or 'no'."
    raw = ocr_with_gemini(model, [image_path], instruction)
    return "yes" in raw.lower()

# ── DOCUMENT-LEVEL PIPELINE ─────────────────────────────────────

def process_invoices_as_docs(model, uploaded_paths: List[str], field_names: List[str] = None) -> List[Dict[str, Any]]:
    """
    Group multi-page PDFs into single documents, run OCR→verify→enrich in parallel,
    then return exactly one invoice dict per document (the first page's result).
    """
    # 1) Group pages by document stem
    doc_to_pages: Dict[str, List[str]] = defaultdict(list)
    for path in uploaded_paths:
        stem = Path(path).stem
        if path.lower().endswith('.pdf'):
            pages = batch_convert_pdfs_to_images([path], "images")
            doc_to_pages[stem].extend(pages)
        else:
            doc_to_pages[stem].append(path)

    # 2) Worker: runs OCR→verify→enrich for one document
    def process_doc(item) -> List[Dict[str, Any]]:
        stem, pages = item
        extracted = ocr_financial_document(model, pages, field_names)
        verified = verify_financial_extraction(model, pages, extracted, field_names)
        enriched = enrich_with_other_options(verified, field_names)
        # tag each dict with its doc stem & image path
        for inv in enriched:
            inv["__doc_stem"] = stem
            # __image_path already set by verify_financial_extraction
        return enriched

    # 3) Dispatch all docs in parallel
    all_invoices: List[Dict[str, Any]] = []
    with ThreadPoolExecutor() as exe:
        # exe.map preserves document order
        for inv_list in exe.map(process_doc, doc_to_pages.items()):
            all_invoices.extend(inv_list)

    # 4) From potentially many pages/doc, pick *one* invoice per doc_stem
    seen = set()
    filtered: List[Dict[str, Any]] = []
    for inv in all_invoices:
        stem = inv["__doc_stem"]
        if stem not in seen:
            filtered.append(inv)
            seen.add(stem)

    return filtered

# ── PAGE-LEVEL: PER-PAGE FUNCTIONS ───────────────────────────────

def ocr_financial_document(model, image_paths: List[str], field_names: List[str] = None) -> List[Dict[str, Any]]:
    """
    Run OCR on each image, parse out the JSON, and return a list of invoice dicts.
    """
    if isinstance(image_paths, str):
        folder = Path(image_paths)
        image_paths = sorted(
            str(p) for ext in ("*.jpg", "*.png", "*.jpeg")
            for p in folder.glob(ext)
        )

    # Use dynamic field configuration if available
    field_manager = FieldConfigManager()
    if field_names:
        instruction = field_manager.generate_extraction_prompt(field_names)
    else:
        # Fallback to default instruction
        instruction = """
        You are an expert in finance and text extraction. Analyze the provided image and determine if it is an invoice. 
        An invoice must include clear payment/total payment amount. If the image contains this and can be identified as an invoice, 
        extract every label and its corresponding value. Format the output as JSON.

        Fields to extract (Nothing Else):
            1. invoice_type (Commercial or Sales Tax)
            2. invoice_number
            3. buyer_name
            4. supplier_name
            5. invoice_date (format: DD-MM-YYYY)
            6. total_invoice_amount (must be numeric, cannot be empty or zero)
            7. sales_tax_amount (if not found, leave empty)
            8. currency (PKR if not found)
            9. po_numbers (array of numbers only, must have PO labels)
            10. delivery_challan_number (DCN/Delivery Order/Challan #)
            11. hs_code (if not found, leave empty)
            12. ntn_no (if not found, leave empty)

        Guard Rails:
            - Convert Urdu text to English
            - PO Numbers must be numeric and have proper PO labels
            - Total amount cannot be empty or zero
            - Only pick Delivery Challan from proper labels, not Gate Pass
            - Use DD-MM-YYYY date format
            - Currency defaults to PKR
            
        Return as JSON array: [{"field_name": "value", ...}]
        """

    def process(img_path: str) -> List[Dict[str, Any]]:
        raw = ocr_with_gemini(model, [img_path], instruction)
        try:
            items = extract_json(raw)
        except ValueError:
            items = []
        for it in items:
            it["__image_path"] = img_path
        return items

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor() as exe:
        for inv_list in exe.map(process, image_paths):
            results.extend(inv_list)
    return results

def verify_financial_extraction(
    model,
    image_paths: List[str],
    extracted_invoices: List[Dict[str, Any]],
    field_names: List[str] = None
) -> List[Dict[str, Any]]:
    """
    Verify or correct each extracted invoice dict against its own pages.
    """
    if not extracted_invoices:
        return []

    # Use dynamic field configuration if available
    field_manager = FieldConfigManager()
    if field_names:
        instruction = field_manager.generate_verification_prompt(field_names)
    else:
        # Fallback to default instruction
        instruction = """
        You are a financial-OCR validator. Below is the JSON extracted from the document plus the image itself.
        Check every field against the images and fix any mistakes or fill in missing values.
        
        Validation Rules:
        - Total amount cannot be empty or zero
        - Currency must be PKR if not found
        - PO numbers must be numeric with proper PO labels
        - Delivery Challan only from proper labels (not Gate Pass)
        - Date format: DD-MM-YYYY
        - Convert Urdu to English
        
        Return corrected JSON in same format.
        """

    def process(inv: Dict[str, Any]) -> Dict[str, Any]:
        img_path = inv["__image_path"]
        payload = json.dumps([inv], ensure_ascii=False, indent=2)
        prompt = instruction + "\nExtracted JSON:\n" + payload
        raw = ocr_with_gemini(model, [img_path], prompt)
        try:
            fixed = extract_json(raw)[0]
        except Exception:
            fixed = inv.copy()
        fixed["__image_path"] = img_path
        return fixed

    with ThreadPoolExecutor() as exe:
        verified = list(exe.map(process, extracted_invoices))

    return verified

# ── REASONING AGENT ─────────────────────────────────────────────

def reasoning_agent(image_path: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Runs a dedicated prompt to gather all options+scores+reason for each field.
    """
    # Configure Gemini with the provided API key
    genai.configure(api_key=api_key)
    
    base_instruction = """You are an expert in finance document analysis. For the provided invoice image,
extract the following fields and provide alternative options where uncertainty exists:

Fields to extract:
  1. invoice_number
  2. supplier_name
  3. invoice_date
  4. total_invoice_amount
  5. po_numbers
  6. delivery_challan_number
  7. sales_tax_amount
  8. hs_code
  9. ntn_no

For each field, provide:
  - Primary extracted value
  - Alternative options if uncertain (with confidence scores 0-100)
  - Reason for uncertainty if applicable

Output format:
[
  {
    "invoice_number": {
      "options": [{"option": "INV-2023-001", "score": 80}, {"option": "INV-2023-002", "score": 20}],
      "reason": "Handwritten text partially unclear"
    },
    "supplier_name": {
      "options": [{"option": "ABC Textiles", "score": 100}]
    }
  }
]

Guard Rails:
- Convert Urdu text to English
- Date format: DD-MM-YYYY
- PO numbers must be numeric
- Total amount cannot be zero
- Only use proper Delivery Challan labels
"""

    try:
        img = Image.open(image_path)
        model = GenerativeModel(
            model_name="gemini-2.0-flash-exp",
            generation_config={"temperature": 0.8}
        )
        response = model.generate_content([base_instruction, img])
        raw = response.text

        # Extract JSON from response
        fence_pattern = r'```json\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```'
        m = re.search(fence_pattern, raw, flags=re.DOTALL)
        payload = m.group(1) if m else raw.strip()

        if payload.lstrip().startswith('{'):
            payload = f'[{payload}]'

        data = json.loads(payload)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"reasoning_agent error: {e}")
        return []

# ── ENRICHMENT: OTHER OPTIONS ───────────────────────────────────

def enrich_with_other_options(invoices: List[Dict[str, Any]], field_names: List[str] = None) -> List[Dict[str, Any]]:
    """
    Add 'other_options' to each verified invoice dict using reasoning_agent,
    without altering existing fields, preserving order exactly.
    """
    # Get API key from Streamlit secrets or environment variable
    api_key = None
    try:
        import streamlit as st
        api_key = st.secrets["api_keys"]["GEMINI_API_KEY"]
    except:
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("Warning: GEMINI_API_KEY not found in secrets or environment variables")
        return invoices  # Return without enrichment instead of empty list
    
    def work(inv: Dict[str, Any]) -> Dict[str, Any]:
        img = inv.get("__image_path")
        if not img:
            return inv

        details = reasoning_agent(img, api_key)
        other: Dict[str, Any] = {}
        if details and isinstance(details, list):
            info = details[0]
            for human_label, payload in info.items():
                if not isinstance(payload, dict):
                    continue
                raw_opts = payload.get("options") or []
                pairs: List[List[Any]] = []

                # Process options
                if all(isinstance(o, dict) and "option" in o and "score" in o for o in raw_opts):
                    for d in raw_opts:
                        pairs.append([d["option"], d["score"]])
                else:
                    # Handle flat list format
                    it = iter(raw_opts)
                    for val, score in zip(it, it):
                        try:
                            sc = float(score)
                        except Exception:
                            sc = None
                        pairs.append([val, sc])

                # Only keep fields with multiple options
                if len(pairs) > 1:
                    key = human_label.lower().replace(" ", "_")
                    other[key] = {
                        "options": pairs,
                        "reason": payload.get("reason")
                    }

        if other:
            inv["other_options"] = other

        return inv

    with ThreadPoolExecutor() as exe:
        enriched = list(exe.map(work, invoices))
    return enriched