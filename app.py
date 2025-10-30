import streamlit as st
import pandas as pd
import io
import PyPDF2
import xml.etree.ElementTree as ET
import re

st.set_page_config(page_title="FacturaFácil DIAN", layout="centered")
st.title("FacturaFácil DIAN")
st.markdown("### **Sube PDF DIAN → Excel Helisa en 1 segundo**")

uploaded_file = st.file_uploader("Sube factura electrónica (PDF)", type=['pdf'])

def extract_xml_from_pdf(pdf_file):
    """Extrae XML DIAN del PDF"""
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    xml_data = ""
    for page in pdf_reader.pages:
        text = page.extract_text() or ""
        if "CUFE" in text or "<fe:" in text or "xmlns:fe" in text:
            start = text.find("<?xml")
            if start == -1:
                start = text.find("<fe:")
            end = text.find("</fe:ElectronicInvoice>", start)
            if end != -1:
                end += 22
                xml_data = text[start:end]
                break
            elif "CUFE" in text:
                # Busca CUFE como respaldo
                cufe_match = re.search(r'CUFE[^\w]*([a-f0-9]{96})', text)
                if cufe_match:
                    st.warning("XML no encontrado, pero CUFE detectado. Usa IA de respaldo.")
                    return None
    return xml_data

def parse_dian_xml(xml_string):
    """Parsea XML DIAN → datos contables"""
    try:
        root = ET.fromstring(xml_string)
        ns = {
            'fe': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
        }
        
        # NIT Proveedor
        nit_elem = root.find('.//cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID', ns)
        nit = nit_elem.text if nit_elem is not None else ""
        
        # Fecha
        fecha_elem = root.find('.//cbc:IssueDate', ns)
        fecha_raw = fecha_elem.text if fecha_elem is not None else ""
        if len(fecha_raw) == 10:
            fecha = f"{fecha_raw[8:10]}/{fecha_raw[5:7]}/{fecha_raw[:4]}"
        else:
            fecha = ""
        
        # Número Factura
        factura_elem = root.find('.//cbc:ID', ns)
        factura = factura_elem.text if factura_elem is not None else ""
        
        # Proveedor
        proveedor_elem = root.find('.//cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName', ns)
        proveedor = proveedor_elem.text if proveedor_elem is not None else ""
        
        # Total
        total_elem = root.find('.//cac:LegalMonetaryTotal/cbc:PayableAmount', ns)
        total = total_elem.text if total_elem is not None else "0"
        
        # Subtotal
        subtotal_elem = root.find('.//cac:LegalMonetaryTotal/cbc:LineExtensionAmount', ns)
        subtotal = subtotal_elem.text if subtotal_elem is not None else "0"
        
        # IVA
        iva_elem = root.find('.//cac:TaxTotal/cbc:TaxAmount', ns)
        iva = iva_elem.text if iva_elem is not None else "0"
        
        return {
            'Fecha': fecha,
            'N° Factura': factura,
            'NIT': nit,
            'Proveedor': proveedor,
            'Subtotal': subtotal,
            'IVA': iva,
            'Total': total
        }
    except Exception as e:
        st.error(f"Error parseando XML: {e}")
        return None

if uploaded_file is not None:
    with st.spinner("Leyendo XML DIAN del PDF..."):
        xml_str = extract_xml_from_pdf(uploaded_file)
        if xml_str:
            data = parse_dian_xml(xml_str)
            if data and data['Total'] != "0":
                st.success("¡Factura DIAN leída 100% automático!")
                st.write(f"**N° Factura:** {data['N° Factura']}")
                st.write(f"**NIT:** {data['NIT']}")
                st.write(f"**Total:** ${data['Total']}")
                
                # Genera Excel Helisa
                df = pd.DataFrame([{
                    'Fecha': data['Fecha'],
                    'Comprobante': data['N° Factura'],
                    'NIT': data['NIT'],
                    'Tercero': data['Proveedor'],
                    'Débito': data['Total'].replace('.', ''),
                    'Crédito': '',
                    'C. Costo': '001',
                    'Cuenta': '510505',
                    'Descripción': f"Factura DIAN {data['N° Factura']}"
                }])
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, sheet_name='Movimientos', index=False)
                output.seek(0)
                
                st.download_button(
                    label="Descargar Excel para Helisa",
                    data=output,
                    file_name=f"DIAN_{data['N° Factura']}.xls",
                    mime="application/vnd.ms-excel"
                )
                st.balloons()
            else:
                st.error("No se pudo leer el XML. ¿Es factura electrónica DIAN?")
        else:
            st.error("No se encontró XML en el PDF. Prueba con otra factura.")
