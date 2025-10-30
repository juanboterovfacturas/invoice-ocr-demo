import streamlit as st
import google.generativeai as genai
import pandas as pd
import io
import json
from pdf2image import convert_from_bytes
from PIL import Image

# === TU API KEY (PEGA TU CLAVE REAL) ===
genai.configure(api_key="AIzaSyC8icWu2kap3RxvMTv7n4VtcaPikeifjHg")  # ← TU CLAVE
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="FacturaFácil AUTO", layout="wide")
st.title("FacturaFácil AUTO - 100% Automático")
st.markdown("**Sube PDF → 3 segundos → Excel Helisa**")

uploaded_file = st.file_uploader("Sube factura (PDF o foto)", type=['pdf', 'png', 'jpg'])

if uploaded_file is not None:
    with st.spinner("Leyendo con IA de Google..."):
        # Convierte a imagen
        images = convert_from_bytes(uploaded_file.read(), dpi=300, first_page=1, last_page=1)
        img = images[0]
        st.image(img, caption="Factura detectada", use_column_width=True)
        
        # PROMPT CORREGIDO (ESTE SÍ FUNCIONA)
        prompt = """FACTURA COLOMBIANA - EXTRAER DATOS EXACTOS

De esta imagen, extrae SOLO:
- Fecha (dd/mm/yyyy)
- N° Factura (RC 6655, FECN-48459, etc.)
- NIT del proveedor (solo números y guiones)
- Nombre del proveedor
- Total a Pagar (solo números)

RESPUESTA SOLO JSON VÁLIDO:
{
  "Fecha": "29/09/2025",
  "N° Factura": "FECN-48459",
  "NIT": "810006056-8",
  "Proveedor": "ALMACEN EL RUIZ",
  "Total": "1798875"
}"""

        try:
            response = model.generate_content([prompt, img])
            data = json.loads(response.text)
            
            st.success("¡Factura leída 100% automático!")
            st.write(f"**Factura:** {data.get('N° Factura', 'N/A')}")
            st.write(f"**NIT:** {data.get('NIT', 'N/A')}")
            st.write(f"**Proveedor:** {data.get('Proveedor', 'N/A')}")
            st.write(f"**Total:** ${data.get('Total', '0')}")

            # Excel para Helisa
            df = pd.DataFrame([{
                'Fecha': data.get('Fecha', ''),
                'Comprobante': data.get('N° Factura', ''),
                'NIT': data.get('NIT', ''),
                'Tercero': data.get('Proveedor', ''),
                'Débito': data.get('Total', '0'),
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
            
        except Exception as e:
            st.error(f"Error: {e}")
            st.write("Intenta con otra factura.")
