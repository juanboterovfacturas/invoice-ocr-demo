import streamlit as st
import pandas as pd
import io
import PyPDF2
import xml.etree.ElementTree as ET
import re
from pdf2image import convert_from_bytes
from PIL import Image
import google.generativeai as genai
import json

# === TU API KEY DE GEMINI (PEGA AQUÍ) ===
genai.configure(api_key="AIzaSyC8icWu2kap3RxvMTv7n4VtcaPikeifjHg")  # ← TU CLAVE REAL
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="FacturaFácil DIAN", layout="centered")
st.title("FacturaFácil DIAN")
st.markdown("### **Sube PDF → Excel Helisa 100% automático**")

uploaded_file = st.file_uploader("Sube factura electrónica DIAN (PDF)", type=['pdf'])

def extract_xml_from_pdf(pdf_bytes):
    """Busca XML DIAN en el PDF"""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            text = page.extract_text() or ""
            if "CUFE" in text or "<fe:" in text:
                # Busca inicio del XML
                start = text.find("<?xml")
                if start == -1:
                    start = text.find("<fe:")
                end = text.find("</fe:ElectronicInvoice>", start)
                if end != -1:
                    end += 22
                    return text[start:end]
                # Alternativa: busca todo el bloque XML
                xml_match = re.search(r'(<\?xml.*</fe:ElectronicInvoice>)', text, re.DOTALL)
                if xml_match:
                    return xml_match.group(1)
    except:
        pass
    return None

def parse_dian_xml(xml_str):
    """Extrae datos del XML DIAN"""
    try:
        root = ET.fromstring(xml_str)
        ns = {
            'fe': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
        }
        
        nit = root.find('.//cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID', ns)
        nit = nit.text if nit is not None else ""
        
        fecha = root.find('.//cbc:IssueDate', ns)
        fecha_raw = fecha.text if fecha is not None else ""
        fecha = f"{fecha_raw[8:10]}/{fecha_raw[5:7]}/{fecha_raw[:4]}" if len(fecha_raw) == 10 else ""
        
        factura = root.find('.//cbc:ID', ns)
        factura = factura.text if factura is not None else ""
        
        proveedor = root.find('.//cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName', ns)
        proveedor = proveedor.text if proveedor is not None else ""
        
        total = root.find('.//cac:LegalMonetaryTotal/cbc:PayableAmount', ns)
        total = total.text if total is not None else "0"
        
        return {
            'Fecha': fecha,
            'N° Factura': factura,
            'NIT': nit,
            'Proveedor': proveedor,
            'Total': total
        }
    except Exception as e:
        st.write(f"Error XML: {e}")
        return None

def ocr_fallback(pdf_bytes):
    """Respaldo: OCR + Gemini IA"""
    try:
        images = convert_from_bytes(pdf_bytes, dpi=300, first_page=1, last_page=1)
        img = images[0]
        st.image(img, caption="Factura detectada", use_column_width=True)
        
        prompt = """
        Extrae de esta factura colombiana:
        - Fecha (dd/mm/yyyy)
        - N° Factura
        - NIT del proveedor
        - Nombre del proveedor
        - Total a Pagar

        Devuelve JSON válido:
        {"Fecha": "05/09/2025", "N° Factura": "FECN-48459", "NIT": "810006056-8", "Proveedor": "ALMACEN EL RUIZ", "Total": "1798875"}
        """
        response = model.generate_content([prompt, img])
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Error OCR: {e}")
        return None

if uploaded_file is not None:
    pdf_bytes = uploaded_file.read()
    
    with st.spinner("Buscando XML DIAN..."):
        xml_str = extract_xml_from_pdf(pdf_bytes)
        
        if xml_str:
            data = parse_dian_xml(xml_str)
            if data and data['Total'] != "0":
                st.success("¡XML DIAN leído 100% automático!")
            else:
                st.warning("XML incompleto → Usando IA + OCR")
                data = ocr_fallback(pdf_bytes)
        else:
            st.warning("No hay XML → Usando IA + OCR")
            data = ocr_fallback(pdf_bytes)
    
    if data:
        st.write(f"**Factura:** {data.get('N° Factura', 'N/A')}")
        st.write(f"**NIT:** {data.get('NIT', 'N/A')}")
        st.write(f"**Proveedor:** {data.get('Proveedor', 'N/A')}")
        st.write(f"**Total:** ${data.get('Total', '0')}")

        # Genera Excel para Helisa
        df = pd.DataFrame([{
            'Fecha': data.get('Fecha', ''),
            'Comprobante': data.get('N° Factura', ''),
            'NIT': data.get('NIT', ''),
            'Tercero': data.get('Proveedor', ''),
            'Débito': data.get('Total', '0').replace('.', '').replace(',', ''),
            'Crédito': '',
            'C. Costo': '001',
            'Cuenta': '510505',
            'Descripción': f"Factura {data.get('N° Factura', '')}"
        }])
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Movimientos', index=False)
        output.seek(0)
        
        st.download_button(
            label="Descargar Excel para Helisa",
            data=output,
            file_name=f"factura_{data.get('N° Factura', 'sin_num')}.xls",
            mime="application/vnd.ms-excel"
        )
        st.balloons()
    else:
        st.error("No se pudo leer la factura. Prueba con otra.")
