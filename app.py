import streamlit as st
import google.generativeai as genai
import pandas as pd
import io
import json
from pdf2image import convert_from_bytes
from PIL import Image

# === TU API KEY ===
genai.configure(api_key="AIzaSyC8icWu2kap3RxvMTv7n4VtcaPikeifjHg")  # ← TU CLAVE
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="FacturaFácil AUTO", layout="wide")
st.title("🤖 **FacturaFácil AUTO** - **100% Automático**")
st.markdown("**Sube PDF → 3 segundos → Excel Helisa**")

uploaded_file = st.file_uploader("🚀 Sube factura (PDF o foto)", type=['pdf', 'png', 'jpg'])

if uploaded_file is not None:
    with st.spinner("🔍 Leyendo con IA de Google..."):
        # Convierte PDF a imagen
        images = convert_from_bytes(uploaded_file.read(), dpi=300)
        img = images[0]
        st.image(img, caption="Factura detectada", use_column_width=True)
        
        # IA extrae TODO
        prompt = """
        **FACTURA COLOMBIANA - EXTRAIGE TODO AUTOMÁTICO**

        De esta factura, extrae EXACTAMENTE:
        ✅ **Fecha** (dd/mm/yyyy)
        ✅ **N° Factura** (FECN-48459, RC 6655, FE...)
        ✅ **NIT Proveedor** (900123456-1)
        ✅ **Proveedor** (nombre completo)
        ✅ **Total** (solo números: 1798875)

        **RESPUESTA SOLO JSON:**
        {
          "Fecha": "29
