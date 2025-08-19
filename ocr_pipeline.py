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
    print(f"🔍 DEBUG: batch_convert_pdfs_to_images called with {len(pdf_paths)} PDFs")
    print(f"🔍 DEBUG: Output folder: {base_output_folder}, DPI: {dpi}")
    
    def worker(pdf_path: str) -> List[str]:
        stem = Path(pdf_path).stem
        out_folder = os.path.join(base_output_folder, stem)
        print(f"🔍 DEBUG: Converting PDF {stem} to images in {out_folder}")
        try:
            result = convert_pdf_to_images(pdf_path, out_folder, dpi)
            print(f"🔍 DEBUG: PDF {stem} converted to {len(result)} images")
            return result
        except Exception as e:
            print(f"❌ DEBUG: Error converting PDF {stem}: {e}")
            import traceback
            print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
            return []

    all_images: List[str] = []
    try:
        with ThreadPoolExecutor() as exe:
            for img_list in exe.map(worker, pdf_paths):
                all_images.extend(img_list)
        print(f"🔍 DEBUG: Batch conversion complete. Total images: {len(all_images)}")
        return all_images
    except Exception as e:
        print(f"❌ DEBUG: Error in batch PDF conversion: {e}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        return []

def convert_pdf_to_images(pdf_path: str, output_folder: str, dpi: int = 300) -> List[str]:
    print(f"🔍 DEBUG: convert_pdf_to_images called for {Path(pdf_path).name}")
    print(f"🔍 DEBUG: PDF exists: {os.path.exists(pdf_path)}")
    print(f"🔍 DEBUG: PDF size: {os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 'N/A'} bytes")
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"🔍 DEBUG: Created output folder: {output_folder}")

    filename = Path(pdf_path).stem
    
    try:
        print(f"🔍 DEBUG: Starting PDF conversion using pdf2image...")
        images = convert_from_path(pdf_path, dpi=dpi)
        print(f"🔍 DEBUG: PDF converted to {len(images)} page images")
        
        image_paths: List[str] = []
        for i, image in enumerate(images, start=1):
            image_name = f"{filename}_page_{i}.jpg"
            image_path = os.path.join(output_folder, image_name)
            
            print(f"🔍 DEBUG: Saving page {i} as {image_name}")
            image.save(image_path, "JPEG")
            print(f"🔍 DEBUG: Saved image: {image_path} ({os.path.getsize(image_path)} bytes)")
            
            image_paths.append(image_path)
        
        print(f"🔍 DEBUG: PDF conversion complete. Generated {len(image_paths)} images")
        return image_paths
        
    except Exception as e:
        print(f"❌ DEBUG: PDF conversion failed for {Path(pdf_path).name}: {e}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        return []

# ── OCR & JSON Extraction ────────────────────────────────────────

def ocr_with_gemini(model, image_paths: List[str], instruction: str) -> str:
    """Process images with Gemini for OCR"""
    print(f"🔍 DEBUG: OCR with Gemini called with {len(image_paths)} images")
    print(f"🔍 DEBUG: Image paths: {image_paths}")
    print(f"🔍 DEBUG: Instruction length: {len(instruction)} chars")
    
    try:
        images = [Image.open(p) for p in image_paths]
        print(f"🔍 DEBUG: Successfully loaded {len(images)} images")
        
        prompt = f"""
    {instruction}
    
    Analyze the provided invoice image(s) and extract the required information accurately.
    """
        print(f"🔍 DEBUG: Final prompt length: {len(prompt)} chars")
        
        response = model.generate_content([prompt, *images])
        print(f"🔍 DEBUG: Got response from Gemini API")
        print(f"🔍 DEBUG: Response text length: {len(response.text)} chars")
        print(f"🔍 DEBUG: Response text preview: {response.text[:200]}...")
        
        return response.text
    except Exception as e:
        print(f"❌ DEBUG: OCR with Gemini failed: {e}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        raise

def extract_json(raw_text: str) -> List[Dict[str, Any]]:
    """
    Extract the first JSON array or object from raw_text (with or without ```json fences```).
    Returns a Python list of dicts.
    """
    print(f"🔍 DEBUG: extract_json called with text length: {len(raw_text)}")
    print(f"🔍 DEBUG: Raw text preview: {raw_text[:300]}...")
    
    fence_pattern = r'```json\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```'
    m = re.search(fence_pattern, raw_text, flags=re.DOTALL)
    payload = m.group(1) if m else raw_text.strip()
    
    print(f"🔍 DEBUG: JSON fence pattern match: {bool(m)}")
    print(f"🔍 DEBUG: Payload after fence extraction: {payload[:200]}...")

    if payload.lstrip().startswith('{'):
        payload = f'[{payload}]'
        print(f"🔍 DEBUG: Wrapped single object in array")

    try:
        data = json.loads(payload)
        print(f"🔍 DEBUG: Successfully parsed JSON")
        if not isinstance(data, list):
            data = [data] if isinstance(data, dict) else []
            print(f"🔍 DEBUG: Converted to list format")
        print(f"🔍 DEBUG: Final extracted data: {len(data)} items")
        if data:
            print(f"🔍 DEBUG: First item preview: {str(data[0])[:200]}...")
        return data
    except json.JSONDecodeError as e:
        print(f"❌ DEBUG: Failed to parse JSON: {str(e)}")
        print(f"❌ DEBUG: Problematic payload: {payload[:200]}...")
        return []

def is_invoice(model, image_path: str) -> bool:
    """
    Check if the image is an invoice by running OCR and checking for specific keywords.
    """
    print(f"🔍 DEBUG: is_invoice called for: {image_path}")
    instruction = "Is this image an invoice? Answer with 'yes' or 'no'."
    raw = ocr_with_gemini(model, [image_path], instruction)
    result = "yes" in raw.lower()
    print(f"🔍 DEBUG: is_invoice result: {result} (raw: '{raw[:100]}...')")
    return result

# ── DOCUMENT-LEVEL PIPELINE ─────────────────────────────────────

def process_invoices_as_docs(model, uploaded_paths: List[str], field_names: List[str] = None) -> List[Dict[str, Any]]:
    """
    Group multi-page PDFs into single documents, run OCR→verify→enrich in parallel,
    then return exactly one invoice dict per document (the first page's result).
    """
    print(f"🔍 DEBUG: Starting processing with {len(uploaded_paths)} files")
    print(f"🔍 DEBUG: Files: {uploaded_paths}")
    print(f"🔍 DEBUG: Field names: {field_names}")
    
    # 1) Group pages by document stem
    doc_to_pages: Dict[str, List[str]] = defaultdict(list)
    for path in uploaded_paths:
        stem = Path(path).stem
        print(f"🔍 DEBUG: Processing file: {path} (stem: {stem})")
        if path.lower().endswith('.pdf'):
            try:
                print(f"🔍 DEBUG: Converting PDF to images...")
                pages = batch_convert_pdfs_to_images([path], "images")
                print(f"🔍 DEBUG: PDF converted to {len(pages)} pages: {pages}")
                doc_to_pages[stem].extend(pages)
            except Exception as e:
                print(f"❌ DEBUG: PDF conversion failed: {e}")
                import traceback
                print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
                return []
        else:
            print(f"🔍 DEBUG: Adding image file directly: {path}")
            doc_to_pages[stem].append(path)
    
    print(f"🔍 DEBUG: Document pages grouped: {dict(doc_to_pages)}")

    # 2) Worker: runs OCR→verify→enrich for one document
    def process_doc(item) -> List[Dict[str, Any]]:
        stem, pages = item
        print(f"🔍 DEBUG: Processing document {stem} with {len(pages)} pages")
        try:
            extracted = ocr_financial_document(model, pages, field_names)
            print(f"🔍 DEBUG: OCR extracted {len(extracted)} invoices: {extracted}")
            
            verified = verify_financial_extraction(model, pages, extracted, field_names)
            print(f"🔍 DEBUG: Verification returned {len(verified)} invoices")
            
            enriched = enrich_with_other_options(verified, field_names)
            print(f"🔍 DEBUG: Enrichment returned {len(enriched)} invoices")
            
            # tag each dict with its doc stem & image path
            for inv in enriched:
                inv["__doc_stem"] = stem
                # __image_path already set by verify_financial_extraction
            return enriched
        except Exception as e:
            print(f"❌ DEBUG: Error processing document {stem}: {e}")
            import traceback
            print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
            return []

    # 3) Dispatch all docs in parallel
    print(f"🔍 DEBUG: Starting parallel processing of {len(doc_to_pages)} documents")
    all_invoices: List[Dict[str, Any]] = []
    try:
        with ThreadPoolExecutor() as exe:
            # exe.map preserves document order
            for inv_list in exe.map(process_doc, doc_to_pages.items()):
                print(f"🔍 DEBUG: Got {len(inv_list)} invoices from document processing")
                all_invoices.extend(inv_list)
    except Exception as e:
        print(f"❌ DEBUG: Error in parallel processing: {e}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        return []

    print(f"🔍 DEBUG: Total invoices collected: {len(all_invoices)}")

    # 4) From potentially many pages/doc, pick *one* invoice per doc_stem
    seen = set()
    filtered: List[Dict[str, Any]] = []
    for inv in all_invoices:
        stem = inv["__doc_stem"]
        if stem not in seen:
            filtered.append(inv)
            seen.add(stem)

    print(f"🔍 DEBUG: Final filtered results: {len(filtered)} invoices")
    return filtered

# ── PAGE-LEVEL: PER-PAGE FUNCTIONS ───────────────────────────────

def ocr_financial_document(model, image_paths: List[str], field_names: List[str] = None) -> List[Dict[str, Any]]:
    """
    Run OCR on each image, parse out the JSON, and return a list of invoice dicts.
    """
    print(f"🔍 DEBUG: OCR starting with {len(image_paths)} image paths: {image_paths}")
    
    if isinstance(image_paths, str):
        folder = Path(image_paths)
        image_paths = sorted(
            str(p) for ext in ("*.jpg", "*.png", "*.jpeg")
            for p in folder.glob(ext)
        )
        print(f"🔍 DEBUG: Converted folder to image paths: {image_paths}")

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
        print(f"🔍 DEBUG: Processing single image: {img_path}")
        try:
            raw = ocr_with_gemini(model, [img_path], instruction)
            print(f"🔍 DEBUG: Got raw OCR response for {Path(img_path).name}")
            
            items = extract_json(raw)
            print(f"🔍 DEBUG: Extracted {len(items)} items from {Path(img_path).name}")
            
            for it in items:
                it["__image_path"] = img_path
                print(f"🔍 DEBUG: Tagged item with image path: {Path(img_path).name}")
            
            return items
        except Exception as e:
            print(f"❌ DEBUG: Error processing {Path(img_path).name}: {e}")
            import traceback
            print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
            return []

    print(f"🔍 DEBUG: Starting parallel OCR processing of {len(image_paths)} images")
    results: List[Dict[str, Any]] = []
    try:
        with ThreadPoolExecutor() as exe:
            for inv_list in exe.map(process, image_paths):
                print(f"🔍 DEBUG: Got {len(inv_list)} items from parallel processing")
                results.extend(inv_list)
    except Exception as e:
        print(f"❌ DEBUG: Error in parallel OCR processing: {e}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        return []
    
    print(f"🔍 DEBUG: OCR processing complete. Total results: {len(results)}")
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
    print(f"🔍 DEBUG: verify_financial_extraction called with {len(extracted_invoices)} invoices")
    
    if not extracted_invoices:
        print(f"🔍 DEBUG: No invoices to verify, returning empty list")
        return []

    # Use dynamic field configuration if available
    field_manager = FieldConfigManager()
    if field_names:
        instruction = field_manager.generate_verification_prompt(field_names)
        print(f"🔍 DEBUG: Using dynamic verification prompt")
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
        print(f"🔍 DEBUG: Using fallback verification prompt")

    def process(inv: Dict[str, Any]) -> Dict[str, Any]:
        img_path = inv["__image_path"]
        print(f"🔍 DEBUG: Verifying invoice from {Path(img_path).name}")
        
        try:
            payload = json.dumps([inv], ensure_ascii=False, indent=2)
            prompt = instruction + "\nExtracted JSON:\n" + payload
            
            print(f"🔍 DEBUG: Verification prompt length: {len(prompt)} chars")
            raw = ocr_with_gemini(model, [img_path], prompt)
            
            fixed_list = extract_json(raw)
            if fixed_list:
                fixed = fixed_list[0]
                print(f"🔍 DEBUG: Verification successful for {Path(img_path).name}")
            else:
                fixed = inv.copy()
                print(f"🔍 DEBUG: Verification failed, using original data for {Path(img_path).name}")
                
        except Exception as e:
            print(f"❌ DEBUG: Error verifying {Path(img_path).name}: {e}")
            fixed = inv.copy()
        
        fixed["__image_path"] = img_path
        return fixed

    print(f"🔍 DEBUG: Starting parallel verification of {len(extracted_invoices)} invoices")
    try:
        with ThreadPoolExecutor() as exe:
            verified = list(exe.map(process, extracted_invoices))
        print(f"🔍 DEBUG: Verification complete. Got {len(verified)} verified invoices")
        return verified
    except Exception as e:
        print(f"❌ DEBUG: Error in parallel verification: {e}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        return extracted_invoices  # Return original if verification fails

# ── REASONING AGENT ─────────────────────────────────────────────

def reasoning_agent(image_path: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Runs a dedicated prompt to gather all options+scores+reason for each field.
    """
    print(f"🔍 DEBUG: reasoning_agent called for {Path(image_path).name}")
    
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
        print(f"🔍 DEBUG: Loaded image for reasoning agent")
        
        model = GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={"temperature": 0.8}
        )
        print(f"🔍 DEBUG: Created reasoning model")
        
        response = model.generate_content([base_instruction, img])
        raw = response.text
        print(f"🔍 DEBUG: Got reasoning response, length: {len(raw)} chars")
        print(f"🔍 DEBUG: Reasoning response preview: {raw[:200]}...")

        # Extract JSON from response
        fence_pattern = r'```json\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```'
        m = re.search(fence_pattern, raw, flags=re.DOTALL)
        payload = m.group(1) if m else raw.strip()
        print(f"🔍 DEBUG: Reasoning JSON payload: {payload[:200]}...")

        if payload.lstrip().startswith('{'):
            payload = f'[{payload}]'
            print(f"🔍 DEBUG: Wrapped reasoning JSON in array")

        data = json.loads(payload)
        result = data if isinstance(data, list) else []
        print(f"🔍 DEBUG: Reasoning agent returning {len(result)} items")
        return result
    except Exception as e:
        print(f"❌ DEBUG: reasoning_agent error: {e}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        return []

# ── ENRICHMENT: OTHER OPTIONS ───────────────────────────────────

def enrich_with_other_options(invoices: List[Dict[str, Any]], field_names: List[str] = None) -> List[Dict[str, Any]]:
    """
    Add 'other_options' to each verified invoice dict using reasoning_agent,
    without altering existing fields, preserving order exactly.
    """
    print(f"🔍 DEBUG: enrich_with_other_options called with {len(invoices)} invoices")
    
    # Get API key from Streamlit secrets or environment variable
    api_key = None
    try:
        import streamlit as st
        api_key = st.secrets["api_keys"]["GEMINI_API_KEY"]
        print(f"🔍 DEBUG: Got API key from Streamlit secrets")
    except:
        api_key = os.getenv("GEMINI_API_KEY")
        print(f"🔍 DEBUG: Got API key from environment variables")
    
    if not api_key:
        print("❌ DEBUG: GEMINI_API_KEY not found in secrets or environment variables")
        return invoices  # Return without enrichment instead of empty list
    
    def work(inv: Dict[str, Any]) -> Dict[str, Any]:
        img = inv.get("__image_path")
        print(f"🔍 DEBUG: Enriching invoice from {Path(img).name if img else 'unknown'}")
        
        if not img:
            print(f"🔍 DEBUG: No image path found, skipping enrichment")
            return inv

        try:
            details = reasoning_agent(img, api_key)
            print(f"🔍 DEBUG: Reasoning agent returned {len(details) if details else 0} details")
            
            other: Dict[str, Any] = {}
            if details and isinstance(details, list):
                info = details[0]
                print(f"🔍 DEBUG: Processing {len(info)} fields from reasoning agent")
                
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
                        print(f"🔍 DEBUG: Added ambiguity for field '{key}' with {len(pairs)} options")

            if other:
                inv["other_options"] = other
                print(f"🔍 DEBUG: Added {len(other)} ambiguous fields to invoice")
            else:
                print(f"🔍 DEBUG: No ambiguities found for this invoice")
        except Exception as e:
            print(f"❌ DEBUG: Error enriching invoice from {Path(img).name if img else 'unknown'}: {e}")

        return inv

    print(f"🔍 DEBUG: Starting parallel enrichment of {len(invoices)} invoices")
    try:
        with ThreadPoolExecutor() as exe:
            enriched = list(exe.map(work, invoices))
        print(f"🔍 DEBUG: Enrichment complete. Got {len(enriched)} enriched invoices")
        return enriched
    except Exception as e:
        print(f"❌ DEBUG: Error in parallel enrichment: {e}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        return invoices  # Return original if enrichment fails