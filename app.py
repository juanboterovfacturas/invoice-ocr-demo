import streamlit as st
import google.generativeai as genai
import pandas as pd
import io
import json
from pdf2image import convert_from_bytes
from PIL import Image

# === TU API KEY PERSONAL (OBLIGATORIO) ===
# Ve a: https://aistudio.google.com/app/apikey → Crea clave → PÉGALA AQUÍ
genai.configure(api_key="AIzaSyC8icWu2kap3RxvMTv7n4VtcaPikeifjHg")  # ← PEGA TU CLAVE
model = genai.GenerativeModel('gemini-1.5-flash')  # ← MODELO CORRECTO

st.set_page_config(page_title="FacturaFácil", layout="wide")
st.title("FacturaFácil - 100% Automático")
st.markdown("**Sube PDF → Excel Helisa en 3 segundos**")

uploaded_file = st.file_uploader("Sube factura", type=['pdf', 'png', 'jpg'])

if uploaded_file is not None:
    with st.spinner("Leyendo con IA..."):
        images = convert_from_bytes(uploaded_file.read(), dpi=300, first_page=1, last_page=1)
        img = images[0]
        st.image(img, caption="Factura detectada", use_column_width=True)
        
        prompt = """Extrae SOLO estos datos de la factura:
- N° Factura
- NIT del proveedor
- Nombre del proveedor
- Fecha (dd/mm/yyyy)
- Total a Pagar (solo números)

JSON válido:
{"N° Factura": "", "NIT": "", "Proveedor": "", "Fecha": "", "Total": ""}"""
        
        try:
            response = model.generate_content([prompt, img])
            data = json.loads(response.text)
            
            st.success("¡Listo!")
            st.write(f"**Factura:** {data.get('N° Factura')}")
            st.write(f"**NIT:** {data.get('NIT')}")
            st.write(f"**Proveedor:** {data.get('Proveedor')}")
            st.write(f"**Total:** ${data.get('Total')}")

            df = pd.DataFrame([{
                'Fecha': data.get('Fecha'),
                'Comprobante': data.get('N° Factura'),
                'NIT': data.get('NIT'),
                'Tercero': data.get('Proveedor'),
                'Débito': data.get('Total'),
                'Crédito': '',
                'C. Costo': '001',
                'Cuenta': '510505',
                'Descripción': f"Factura {data.get('N° Factura')}"
            }])
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Movimientos', index=False)
            output.seek(0)
            
            st.download_button(
                "Descargar Excel para Helisa",
                output,
                f"factura_{data.get('N° Factura', 'sin_num')}.xls",
                "application/vnd.ms-excel"
            )
            st.balloons()
            
        except Exception as e:
            st.error(f"Error: {e}")
