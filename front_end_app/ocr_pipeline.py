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

    These pages form a garment tech pack. Extract every field and value into structured JSON, grouping by page and section. Ensure clear keys for page_number, page_title, header_section, spec_tables (with rows), colorway_tables, and color_placement_sequences.
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

    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError(f"Expected list after parsing, got {type(data)}")
    return data

def is_invoice(model, image_path: str) -> bool:
    """
    Check if the image is an invoice by running OCR and checking for specific keywords.
    """
    instruction = "Is this image an invoice? Answer with 'yes' or 'no'."
    raw = ocr_with_gemini(model, [image_path], instruction)
    return "yes" in raw.lower()

# ── DOCUMENT-LEVEL PIPELINE ─────────────────────────────────────

def process_invoices_as_docs(model, uploaded_paths: List[str]) -> List[Dict[str, Any]]:
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
        extracted = ocr_financial_document(model, pages)
        verified  = verify_financial_extraction(model, pages, extracted)
        enriched  = enrich_with_other_options(verified)
        # tag each dict with its doc stem & image path
        for inv in enriched:
            inv["__doc_stem"]     = stem
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
    print(filtered)

    return filtered

# ── PAGE-LEVEL: PER-PAGE FUNCTIONS ───────────────────────────────

def ocr_financial_document(model, image_paths: List[str]) -> List[Dict[str, Any]]:
    """
    Run OCR on each image, parse out the JSON, and return a list of invoice dicts.
    """
    if isinstance(image_paths, str):
        folder = Path(image_paths)
        image_paths = sorted(
            str(p) for ext in ("*.jpg","*.png")
            for p in folder.glob(ext)
        )

    instruction = """
        Consider yourself an expert in finance and text extraction. Analyze the provided image and determine if it is an invoice. An invoice must includes clear payment/total payment amount. If the image contains this and can be identified as an invoice, extract every label and its corresponding value, otherwise ignore the image, 
        do not add any extra text, and format the output as JSON:

        1)Fields to filter and keep (Nothing Else):
            1. Invoice Type (Sales Tax or Commercial)
            2. Invoice Number
            3. Buyer Name
            4. Supplier Name
            5. Invoice date
            6. Total invoice amount (Total Invoice amount cannot be empty or zero. Some times the total invoice amount can be without the label.)
            7. Sales Tax Amount (if not found, leave empty)
            8. Currency (PKR if not found)
            9. PO Numbers (PO NUmbers must be only numericals, if filled. Make absolutely sure that you do only pick them against PO field and not any other field in the document, double check this. Leave empty if not found.)
            10. Delivery Challan Number / DCN / Delivery Order Number / Challan #
            11. HS Code (if not found, leave empty)
            12. NTN No (if not found, leave empty)

        Instruction: For each guard rail, follow a proper chain of thought and reasoning to make sure you are extracting the right information.

        2) Guard Rails:
            - NTN No can be found twice, one will be "06885551" ignore this one and pick the other one.
            - If some extracted text is in Urdu, then convert it to English. Example : انٹر لوپ
            - The No. field is considered the invoice number if invoice label is not mentioned.
            - PO Numbers must have PO labels against them. Example: PO, Purchase Order etc. And they must be numericals
            - Total Invoice amount cannot be empty or zero and it will always be numeric.
            - Sales Tax Amount will always be numeric.
            - If the PO Number label is present in the table, but its value is empty, then the PO Number extracted value should be empty as well and not to be filled with other fields' values like Unit etc.
            - Go through the entire document again to make sure you have the right fields and information and will generate the result if ran again.
            - Only pick Delivery Challan Number/DCN/Deliver Order Number/Challan # against the label. Donot pick it against Gate Pass labels like Gate Pass No . If not sure, leave it empty.

        Negative example:
            Snippet: "Gate Pass No 99474"  
            → "delivery_challan_number": ""

            Snippet: "P.O. # HD 5"
            → "po_numbers": [""]

        Positive example:
            Snippet: "Dc No. 27504"  
            → "delivery_challan_number": "27504"

            Snippet: "PO NO 1229082"  
            → "po_numbers": ["1229082"]

            Snippet: "Party PO 24-10425"
            → "po_numbers": ["24-10425"]
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
    extracted_invoices: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Verify or correct each extracted invoice dict against its own pages.
    """
    if not extracted_invoices:
        return []

    instruction = """
        You are a financial-OCR validator. Below is the JSON extracted from the document plus the image itself. 
        + – Check every field (invoice_number, buyer_name, supplier_name, invoice_date, total_invoice_amount, po_numbers, delivery_challan) against the images. Treat each invoice separate from other invoice.
        + – Fix any mistakes or fill in any missing values if they are clearly visible.
        + – Total Invoice amount cannot be empty or zero. Some times Total invoice amount can be without the label. Where applicable, it is Net Payable including all the taxes.
        + – Currency must be PKR if not found.
        + – Sales Tax Amount (if not found, leave empty)
        + – PO NUmbers must be only numericals, if filled. Make absolutely sure that you do only pick them against PO field and not any other field in the document. Leave empty if not found.
        + – Delivery Challan must come **only** from labels matching “Delivery Challan”, “DCN”, "Challan #" or “Delivery Order.” Do not use Gate Pass labels.
        + – HS Code (if not found, leave empty)
        + – NTN No (if not found, leave empty)
        +
        + **Two Negative examples**:
        +    Gate Pass No → 99474  
        +    → delivery_challan_number = ""

        +    "P.O. # HD 5"  
        +    → "po_numbers": [""]

        + **Three Positive examples**:
        +    Delivery Challan No → 27504  
        +    → delivery_challan_number = "27504"

        +    "PO NO 1229082"  
        +    → "po_numbers": ["1229082"]

        +    "Party PO 24-10425"  
        +    → "po_numbers": ["24-10425"]

        Guard Rails:
            - NTN No can be found twice, one will be "06885551" ignore this one and pick the other one. 
            - If some extracted text is in Urdu, then convert it to English. Example : انٹر لوپ
            - The No. field is considered the invoice number if invoice label is not mentioned.
            - Sales Tax Amount will always be numeric.
            - PO Numbers must have PO labels against them. Example: PO, Purchase Order etc. And they must be numericals
            - Total Invoice amount cannot be empty or zero, Where applicable, it is Net Payable including all the taxes. It should always be numeric.
            - If the PO Number label is present in the table, but its value is empty, then the PO Number extracted value should be empty as well and not to be filled with other fields' values like Unit etc.
            - Only pick Delivery Challan Number/DCN/Deliver Order Number/Challan # against the label. Donot pick it against Gate Pass labels like Gate Pass No . If not sure, leave it empty.
            - Dates should be returned in the format **DD-MM-YYYY**
    """

    def process(inv: Dict[str, Any]) -> Dict[str, Any]:
        img_path = inv["__image_path"]
        payload  = json.dumps([inv], ensure_ascii=False, indent=2)
        prompt   = instruction + "\nExtracted JSON:\n" + payload
        raw      = ocr_with_gemini(model, [img_path], prompt)
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

import re
import json
from PIL import Image
from google.generativeai import GenerativeModel
from typing import List, Dict, Any

def reasoning_agent(image_path: str) -> List[Dict[str, Any]]:
    """
    Runs a dedicated prompt to gather all options+scores+reason for each field.
    """
    base_instruction = """You are an expert in finance document analysis. For each provided image,
extract ONLY the following fields in JSON format:
  1. Invoice Number
  2. Supplier Name
  3. Invoice Date
  4. Total Invoice Amount
  5. PO Numbers
  6. Delivery Challan Number / DCN
  7. Sales Tax Amount (if not found, leave empty)
  8. HS Code (if not found, leave empty)
  9. NTN No (if not found, leave empty)

In addition to each field’s value, provide:
  - A list of strong possible options under the 'options' key. Each option must include:
      - "option": the potential value
      - "score": the probability score (out of 100). All scores combined must sum to 100.
  - If the OCR result contains uncertainty or confusion (e.g., handwriting, blurred digits), 
    return all plausible options under the options list. Clearly state in the "reason" field 
    why there's uncertainty. For instance, "Unclear, possibly '1234560' or '1234550'. 
    Cross-check manually."

Output an array of objects like:
[
  {
    "invoice_number": {
      "options": ["INV-2023-001", 60, "Invoice # INV-2023-001", 40]
    },
    "supplier_name": {
      "options": ["ABC Textiles", 100]
    },
    "invoice_date": {
      "options": ["21/09/2023", 50, "2023-09-21", 50]
    },
    "total_invoice_amount": {
      "options": ["105,000 PKR", 70, "PKR 105000", 30]
    },
    "po_numbers": {
      "options": ["PO-8891", 100]
    },
    "delivery_challan_number": {
      "options": ["DCN-4522", 80, "Delivery Challan #4522", 20]
    }
  }
]

Guard Rails:
  - NTN No can be found twice, one will be "06885551" ignore this one and pick the other one.
  - If any extracted text is in Urdu, convert it to English. Example: انٹر لوپ → Interloop
  - The 'No.' field is considered the invoice number if the invoice label is not mentioned and is located near the header.
  - First part of Supplier name is fixed as Interloop. Add division or unit along with supplier name if it is present in the document. Example: Interloop (HD1 or Spinning Unit). If Division/Unit is present, no need to add just "Interloop Limited".
  - PO Numbers must have PO-related labels against them. Example: PO, PO No., Purchase Order, etc. The values must be numeric or alphanumeric.
  - Total Invoice Amount cannot be empty or zero. Must be found near clear labels like 'Total', 'Invoice Total', 'Grand Total', etc. It should always be numeric.
  - Sales Tax Amount will always be numeric.
  - If the PO Number label is present in the table, but the corresponding value is empty, the extracted PO Number value should also remain empty.
  - Only pick Delivery Challan Number / DCN / Delivery Order Number / Challan # when the appropriate label is found. Do not use Gate Pass labels.
  - If the OCR result is uncertain due to handwriting or unclear digits, return all plausible options and highlight the uncertainty in the "reason" field.
  - Dates should be returned in the format **DD-MM-YYYY** (e.g., 10-05-2024). If the text contains a written format like "10 May 2024" or "May 10, 2024", convert it to "10-05-2024".
"""

    # call Gemini
    img = Image.open(image_path)
    response = GenerativeModel(
        model_name="gemini-2.5-pro",
        generation_config={"temperature": 0.0}
    ).generate_content([base_instruction, img])
    raw = response.text

    # strip ```json fences``` if present
    fence_pattern = r'```json\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```'
    m = re.search(fence_pattern, raw, flags=re.DOTALL)
    payload = m.group(1) if m else raw.strip()

    # wrap single object in list
    if payload.lstrip().startswith('{'):
        payload = f'[{payload}]'

    # parse JSON
    try:
        data = json.loads(payload)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        print("reasoning_agent: failed to parse JSON:", raw)
        return []


# ── ENRICHMENT: OTHER OPTIONS ───────────────────────────────────

def enrich_with_other_options(invoices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add 'other_options' to each verified invoice dict using reasoning_agent,
    without altering existing fields, preserving order exactly.
    """
    def work(inv: Dict[str, Any]) -> Dict[str, Any]:
        img = inv.get("__image_path")
        if not img:
            return inv

        details = reasoning_agent(img)
        other: Dict[str, Any] = {}
        if details and isinstance(details, list):
            info = details[0]
            for human_label, payload in info.items():
                if not isinstance(payload, dict):
                    continue
                raw_opts = payload.get("options") or []
                pairs: List[List[Any]] = []

                # 1) If each item is already a dict, pull out its 'option'/'score'
                if all(isinstance(o, dict) and "option" in o and "score" in o for o in raw_opts):
                    for d in raw_opts:
                        pairs.append([d["option"], d["score"]])

                # 2) Otherwise assume a flat [val,score,val,score,…] list
                else:
                    it = iter(raw_opts)
                    for val, score in zip(it, it):
                        # ensure numeric score
                        try:
                            sc = float(score)
                        except Exception:
                            sc = None
                        pairs.append([val, sc])

                # only keep fields that truly have more than one possibility
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