import streamlit as st
import google.generativeai as genai
import pandas as pd
import io
import re
from PIL import Image
import json
from pdf2image import convert_from_bytes

# --- CONFIGURACIÓN GEMINI ---
genai.configure(api_key="AIzaSyB3cD7fGhJkLmNopQrStUvWxYzAbCdEfGh")  # ← TU CLAVE REAL AQUÍ
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="FacturaFácil.co", layout="centered")
st.title("FacturaFácil.co")
st.markdown("### Sube tu factura → Excel listo para **Helisa Colombia**")

# --- SUBIR ARCHIVO ---
uploaded_file = st.file_uploader("Sube foto o PDF", type=['png', 'jpg', 'jpeg', 'pdf'])

def process_file(uploaded_file):
    """Procesa imagen o PDF y devuelve imagen PIL para Gemini"""
    if uploaded_file.type.startswith('image/'):
        # Imagen directa
        image = Image.open(uploaded_file)
        return [image]
    elif uploaded_file.type == 'application/pdf':
        # PDF: Convierte a imágenes
        st.info("Convirtiendo PDF a imagen...")
        images = convert_from_bytes(uploaded_file.read(), dpi=200)
        return images[:1]  # Solo primera página
    else:
        st.error("Formato no soportado. Usa JPG, PNG o PDF.")
        return None

def extract_with_gemini(image):
    """Extrae datos con Gemini IA"""
    prompt = """
    Extrae de esta factura colombiana (DIAN):
    - Fecha (dd/mm/yyyy)
    - N° Factura (ej: F001-123)
    - NIT proveedor (ej: 900123456-1)
    - Proveedor (nombre)
    - Subtotal
    - IVA (19%)
    - Total

    Responde SOLO JSON válido:
    {
      "Fecha": "15/10/2025",
      "N° Factura": "F001-123",
      "NIT": "900123456-1",
      "Proveedor": "Éxito S.A.",
      "Subtotal": "84034",
      "IVA": "15966",
      "Total": "100000"
    }
    """
    try:
        response = model.generate_content([prompt, image])
        return json.loads(response.text)
    except:
        return {
            'Fecha': '', 'N° Factura': '', 'NIT': '',
            'Proveedor': '', 'Subtotal': '', 'IVA': '', 'Total': ''
        }

if uploaded_file is not None:
    images = process_file(uploaded_file)
    if images:
        # Muestra la primera imagen
        st.image(images[0], caption="Factura detectada", use_column_width=True)
        
        with st.spinner("Analizando con IA de Google..."):
            data = extract_with_gemini(images[0])
        
        # --- FORMULARIO DE EDICIÓN ---
        st.subheader("📋 Datos detectados (corrige si es necesario)")
        col1, col2 = st.columns(2)
        with col1:
            data['Fecha'] = st.text_input("Fecha", data.get('Fecha', ''))
            data['N° Factura'] = st.text_input("N° Factura", data.get('N° Factura', ''))
            data['NIT'] = st.text_input("NIT", data.get('NIT', ''))
        with col2:
            data['Proveedor'] = st.text_input("Proveedor", data.get('Proveedor', ''))
            data['Subtotal'] = st.text_input("Subtotal", data.get('Subtotal', ''))
            data['IVA'] = st.text_input("IVA", data.get('IVA', ''))
            data['Total'] = st.text_input("Total", data.get('Total', ''))
        
        st.subheader("💼 Datos contables para Helisa")
        centro = st.text_input("Centro de Costos", "001")
        cuenta = st.text_input("Cuenta Contable", "510505")
        desc = st.text_area("Descripción", "Compra según factura electrónica")
        
        if st.button("🎯 Generar Excel para Helisa"):
            # Crea DataFrame para Helisa
            df = pd.DataFrame([{
                'Fecha': data['Fecha'],
                'Comprobante': data['N° Factura'],
                'NIT': data['NIT'],
                'Tercero': data['Proveedor'],
                'Débito': data['Total'].replace('.', '').replace(',', ''),
                'Crédito': '',
                'C. Costo': centro,
                'Cuenta': cuenta,
                'Descripción': desc
            }])
            
            # Exporta como .xls
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Movimientos', index=False)
            output.seek(0)
            
            st.download_button(
                label="📥 Descargar Excel (.XLS) para Helisa",
                data=output,
                file_name=f"factura_{data['N° Factura'] or 'sin_numero'}.xls",
                mime="application/vnd.ms-excel"
            )
            st.success("✅ ¡Excel listo! Abrelo y guarda como .XLS (97-2003) para Helisa.")
            st.balloons()
    else:
        st.error("No se pudo procesar el archivo.")

st.markdown("---")
st.caption("💡 Tip: Usa PDFs de facturas electrónicas DIAN o fotos claras.")
