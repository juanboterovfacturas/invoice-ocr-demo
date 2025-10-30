import streamlit as st
import pandas as pd
import io
import re
from pdf2image import convert_from_bytes
from PIL import Image
from paddleocr import PaddleOCR

# Config OCR (español)
ocr = PaddleOCR(use_angle_cls=True, lang='es')

st.set_page_config(page_title="FacturaFácil OCR", layout="wide")
st.title("FacturaFácil OCR - 95% Automático")
st.markdown("**Sube PDF → OCR → Excel Helisa**")

uploaded_file = st.file_uploader("Sube factura", type=['pdf', 'png', 'jpg'])

if uploaded_file is not None:
    with st.spinner("Leyendo con OCR..."):
        # Convierte a imagen
        images = convert_from_bytes(uploaded_file.read(), dpi=300, first_page=1, last_page=1)
        img = images[0]
        st.image(img, caption="Factura detectada", use_column_width=True)
        
        # OCR
        result = ocr.ocr(img, cls=True)
        text = ' '.join([line[1][0] for line in result[0] if line])
        
        # Regex para Colombia
        data = {
            'Fecha': re.search(r'(\d{2}/\d{2}/\d{4})', text) or re.search(r'(\d{2}-\d{2}-\d{4})', text),
            'N° Factura': re.search(r'(FECN|RC|FE)\-?\d+', text) or re.search(r'No\.\s*F[ECR]?\s*(\d+)', text),
            'NIT': re.search(r'(\d{9}\-\d)', text) or re.search(r'NIT[:\s]*(\d{3,9}\-\d)', text),
            'Total': re.search(r'Total\s*a\s*Pagar[:\s]*\$?([\d\.,]+)', text) or re.search(r'Total[:\s]*\$?([\d\.,]+)', text),
            'Proveedor': re.search(r'(ALMACEN|EMPRESA|SA)\s*([A-Z\s]+?)(?=\s*NIT|\s*$)', text, re.I)
        }
        
        # Limpia datos
        fecha = data['Fecha'].group(1) if data['Fecha'] else ""
        factura = data['N° Factura'].group(1) if data['N° Factura'] else ""
        nit = data['NIT'].group(1) if data['NIT'] else ""
        total = data['Total'].group(1) if data['Total'] else "0"
        total = re.sub(r'[.,]', '', total)
        proveedor = data['Proveedor'].group(2).strip() if data['Proveedor'] else "Proveedor desconocido"
        
        st.success("¡Datos extraídos!")
        st.write(f"**Factura:** {factura}")
        st.write(f"**NIT:** {nit}")
        st.write(f"**Proveedor:** {proveedor}")
        st.write(f"**Total:** ${total}")

        # Excel Helisa
        df = pd.DataFrame([{
            'Fecha': fecha,
            'Comprobante': factura,
            'NIT': nit,
            'Tercero': proveedor,
            'Débito': total,
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
            f"factura_{factura or 'sin_num'}.xls",
            "application/vnd.ms-excel"
        )
        st.balloons()
