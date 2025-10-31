import streamlit as st
import pandas as pd
import io
import re
from pdf2image import convert_from_bytes
from PIL import Image
from paddleocr import PaddleOCR

# OCR (una vez)
@st.cache_resource
def load_ocr():
    return PaddleOCR(use_angle_cls=True, lang='es', use_gpu=False)

ocr = load_ocr()

st.set_page_config(page_title="FacturaFácil", layout="centered")
st.title("FacturaFácil - 100% Automático")
st.markdown("**Sube factura DIAN → Excel Helisa**")

uploaded_file = st.file_uploader("Sube PDF", type=['pdf'])

if uploaded_file is not None:
    with st.spinner("Procesando..."):
        images = convert_from_bytes(uploaded_file.read(), dpi=300, first_page=1, last_page=1)
        img = images[0]
        st.image(img, caption="Factura", use_column_width=True)
        
        result = ocr.ocr(img, cls=True)
        text = "\n".join([line[1][0] for line in result[0]])
        
        # REGEX MEJORADO PARA TUS FACTURAS
        factura = re.search(r'No[\.\s]*\s*([A-Z0-9\-]+)', text, re.I) or re.search(r'Factura.*?([A-Z0-9\-]+)', text, re.I)
        nit = re.search(r'NIT[:\.\s]*([\d\.\-]+)', text, re.I)
        proveedor = re.search(r'^(.+?)(?=NIT|Tel|Direcci)', text, re.M) or re.search(r'(.+?)(?=NIT)', text, re.M)
        fecha = re.search(r'(\d{2}[\/\-]\d{2}[\/\-]\d{4})', text)
        total = re.search(r'Total a Pagar[:\.\s]*[\$]?[\d\.,]+', text, re.I) or re.search(r'Total[:\.\s]*[\$]?[\d\.,]+', text, re.I)
        
        # Limpieza
        factura = factura.group(1).strip() if factura else "N/A"
        nit = re.sub(r'\D', '', nit.group(1)) if nit else "N/A"
        proveedor = proveedor.group(1).strip() if proveedor else "N/A"
        fecha = fecha.group(1).replace('-', '/') if fecha else "N/A"
        total_val = re.search(r'[\d\.,]+', total.group(0)).group(0) if total else "0"
        total_val = total_val.replace('.', '').replace(',', '')

        st.success("¡Factura leída 100% automático!")
        st.write(f"**Factura:** {factura}")
        st.write(f"**NIT:** {nit}")
        st.write(f"**Proveedor:** {proveedor}")
        st.write(f"**Fecha:** {fecha}")
        st.write(f"**Total:** ${total_val}")

        df = pd.DataFrame([{
            'Fecha': fecha,
            'Comprobante': factura,
            'NIT': nit,
            'Tercero': proveedor,
            'Débito': total_val,
            'Crédito': '',
            'C. Costo': '001',
            'Cuenta': '510505',
            'Descripción': f"Factura {factura}"
        }])

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Movimientos', index=False)
        output.seek(0)

        st.download_button(
            "Descargar Excel para Helisa",
            output,
            f"factura_{factura}.xls",
            "application/vnd.ms-excel"
        )
        st.balloons()
