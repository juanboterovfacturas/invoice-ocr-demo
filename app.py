import streamlit as st
import pytesseract
from PIL import Image
import pandas as pd
import re
import io

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="FacturaFácil.co", layout="centered")
st.title("FacturaFácil.co")
st.markdown("### Sube tu factura → Excel listo para **Helisa Colombia**")

# --- SUBIR ARCHIVO ---
uploaded_file = st.file_uploader(
    "Sube foto o PDF de la factura",
    type=['png', 'jpg', 'jpeg', 'pdf']
)

def ocr_image(image):
    return pytesseract.image_to_string(image, lang='spa')

def extract_data(text):
    data = {
        'Fecha': '',
        'N° Factura': '',
        'NIT': '',
        'Proveedor': '',
        'Subtotal': '',
        'IVA': '',
        'Total': ''
    }

    # Fecha
    fecha = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', text)
    if fecha: data['Fecha'] = fecha.group(1)

    # Número de factura
    factura = re.search(r'Factura.*?([A-Z0-9\-]+)', text, re.I) or \
              re.search(r'N[º°]?\s*([A-Z0-9\-]+)', text, re.I)
    if factura: data['N° Factura'] = factura.group(1).upper()

    # NIT
    nit = re.search(r'NIT.*?([\d\.\-]{10,15})', text, re.I) or \
          re.search(r'(\d{9}-\d)', text)
    if nit: data['NIT'] = nit.group(1).replace('.', '')

    # Total
    total = re.search(r'Total.*?([\d\.,]+)', text, re.I) or \
            re.search(r'Valor a pagar.*?([\d\.,]+)', text, re.I)
    if total:
        valor = total.group(1).replace('.', '').replace(',', '')
        data['Total'] = valor
        try:
            total_num = float(valor)
            subtotal = round(total_num / 1.19, 0)
            iva = total_num - subtotal
            data['Subtotal'] = f"{subtotal:,.0f}".replace(',', '.')
            data['IVA'] = f"{iva:,.0f}".replace(',', '.')
            data['Total'] = f"{total_num:,.0f}".replace(',', '.')
        except: pass

    return data

# --- PROCESAR ARCHIVO ---
if uploaded_file is not None:
    if uploaded_file.type.startswith('image'):
        image = Image.open(uploaded_file)
        st.image(image, caption="Factura subida", use_column_width=True)
        text = ocr_image(image)
    else:
        st.info("Leyendo PDF... (solo primera página)")
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(uploaded_file.read(), dpi=200)
            text = ocr_image(images[0])
        except:
            st.error("No se pudo leer el PDF. Toma una foto clara.")
            text = ""

    data = extract_data(text)

    # --- FORMULARIO ---
    st.subheader("Datos detectados (corrige si es necesario)")
    col1, col2 = st.columns(2)
    with col1:
        data['Fecha'] = st.text_input("Fecha", data['Fecha'])
        data['N° Factura'] = st.text_input("N° Factura", data['N° Factura'])
        data['NIT'] = st.text_input("NIT", data['NIT'])
    with col2:
        data['Proveedor'] = st.text_input("Proveedor", data['Proveedor'])
        data['Subtotal'] = st.text_input("Subtotal", data['Subtotal'])
        data['IVA'] = st.text_input("IVA", data['IVA'])
        data['Total'] = st.text_input("Total", data['Total'])

    st.subheader("Datos para Helisa")
    centro = st.text_input("Centro de Costos", "001")
    cuenta = st.text_input("Cuenta Contable", "510505")
    desc = st.text_area("Descripción", "Compra según factura")

    if st.button("Generar Excel para Helisa"):
        df = pd.DataFrame([{
            'Fecha': data['Fecha'],
            'Comprobante': data['N° Factura'],
            'NIT': data['NIT'],
            'Tercero': data['Proveedor'],
            'Débito': data['Total'].replace('.', ''),
            'Crédito': '',
            'C. Costo': centro,
            'Cuenta': cuenta,
            'Descripción': desc
        }])

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Movimientos', index=False)
        output.seek(0)

        st.download_button(
            label="Descargar Excel (.XLS)",
            data=output,
            file_name=f"factura_{data['N° Factura'] or 'sin_num'}.xls",
            mime="application/vnd.ms-excel"
        )
        st.success("¡Excel listo para Helisa!")
        st.balloons()
