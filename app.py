import streamlit as st
import google.generativeai as genai
import pandas as pd
import io
import re
from PIL import Image

# --- CONFIGURACIÓN GEMINI ---
genai.configure(api_key="AIzaSyC8icWu2kap3RxvMTv7n4VtcaPikeifjHg") 
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="FacturaFácil.co", layout="centered")
st.title("FacturaFácil.co")
st.markdown("### Sube tu factura → Excel listo para **Helisa Colombia**")

# --- SUBIR ARCHIVO ---
uploaded_file = st.file_uploader("Sube foto o PDF", type=['png', 'jpg', 'jpeg', 'pdf'])

def extract_with_gemini(image):
    prompt = """
    Extrae estos datos de la factura colombiana:
    - Fecha (dd/mm/yyyy)
    - N° Factura
    - NIT del proveedor
    - Subtotal
    - IVA (19%)
    - Total
    - Proveedor (nombre)

    Devuelve SOLO en formato JSON:
    {
      "Fecha": "",
      "N° Factura": "",
      "NIT": "",
      "Proveedor": "",
      "Subtotal": "",
      "IVA": "",
      "Total": ""
    }
    """
    response = model.generate_content([prompt, image])
    return response.text

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Factura subida", use_column_width=True)
    
    with st.spinner("Leyendo factura con IA..."):
        try:
            json_text = extract_with_gemini(image)
            import json
            data = json.loads(json_text)
        except:
            data = {
                'Fecha': '', 'N° Factura': '', 'NIT': '',
                'Proveedor': '', 'Subtotal': '', 'IVA': '', 'Total': ''
            }

    # --- FORMULARIO ---
    st.subheader("Datos detectados")
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
