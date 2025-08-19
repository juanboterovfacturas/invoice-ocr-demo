import os
import time
import json
from pathlib import Path
from typing import List, Dict
from datetime import datetime

import pandas as pd
import streamlit as st
from PIL import Image
from dateutil import parser
import google.generativeai as genai
from google.generativeai import GenerationConfig
from streamlit_lottie import st_lottie
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import requests

from ocr_pipeline import process_invoices_as_docs
from field_config_ui import render_field_config_page, get_preset_selector, get_field_manager

# ── Page Config ────────────────────────────────────────────────
st.set_page_config(
    page_title="Invoice OCR Demo - Moeed's Portfolio", 
    layout="wide",
    page_icon="📄"
)

# ── GLOBAL STYLE OVERRIDES ────────────────────────────────────
st.markdown("""
<style>
    /* Main container styling */
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
    }
    
    /* Card styling */
    .info-card {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        margin-bottom: 1rem;
    }
    
    /* Button styling */
    .stButton>button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: bold;
        transition: transform 0.2s;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* File uploader styling */
    .uploadedFile {
        border: 2px dashed #667eea;
        border-radius: 10px;
        padding: 2rem;
        text-align: center;
        background-color: #f8f9fa;
    }
    
    /* Metrics styling */
    [data-testid="metric-container"] {
        background-color: white;
        border: 1px solid #e0e0e0;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Progress bar */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Navigation container */
    .nav-container {
        background: rgba(102, 126, 234, 0.1);
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        border: 1px solid rgba(102, 126, 234, 0.2);
        text-align: center;
    }
    
    /* Navigation title */
    .nav-title {
        color: #667eea;
        font-weight: bold;
        margin-bottom: 0.5rem;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Load Gemini Model ─────────────────────────────────────────
@st.cache_resource
def load_model():
    # Get API key from Streamlit secrets or environment variable
    try:
        api_key = st.secrets["api_keys"]["GEMINI_API_KEY"]
    except:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            st.error("🔑 **API Key Required**")
            st.markdown("""
            Please configure your Google Gemini API key:
            
            **For Streamlit Cloud:**
            - Add `GEMINI_API_KEY` to your app's secrets
            
            **For Local Development:**
            - Add `GEMINI_API_KEY` to your `.streamlit/secrets.toml` file
            - Or set the `GEMINI_API_KEY` environment variable
            
            Get your API key at: https://makersuite.google.com/app/apikey
            """)
            st.stop()
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        "gemini-2.0-flash-exp",
        generation_config=GenerationConfig(temperature=0.3)
    )

model = load_model()

# ── Lottie Animation ─────────────────────────────────────────
@st.cache_data
def load_lottie_url(url: str):
    try:
        r = requests.get(url, timeout=10)
        return r.json() if r.status_code == 200 else None
    except:
        return None

lottie_anim = load_lottie_url(
    "https://lottie.host/fda0e746-60d5-4120-a918-c79c128b1bef/Ip6YQwzhGA.json"
)

# ── Invoice Pipeline (temporarily uncached for debugging) ─────────────────────────────────
# @st.cache_data(show_spinner=False)  # Disabled caching to see debug output
def load_invoices(_model, paths: tuple, field_names: tuple = None) -> list:
    return process_invoices_as_docs(_model, list(paths), list(field_names) if field_names else None)

# ── Export Functions ──────────────────────────────────────────
def export_to_excel(invoices: List[Dict], filename: str = None) -> str:
    """Export invoices to Excel format"""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"invoice_summary_{timestamp}.xlsx"
    
    if not invoices:
        return ""
    
    # Get field manager for field labels
    field_manager = get_field_manager()
    all_fields = field_manager.get_all_fields()
    
    # Prepare data for Excel
    rows = []
    for inv in invoices:
        row = {}
        
        # Add all non-internal fields
        for key, value in inv.items():
            if key.startswith("__"):
                continue
                
            # Get field label if available
            if key in all_fields:
                label = all_fields[key].label
            else:
                label = key.replace("_", " ").title()
            
            # Format value based on field type
            if isinstance(value, list):
                formatted_value = ", ".join(str(x) for x in value)
            else:
                formatted_value = str(value) if value else ""
                
            row[label] = formatted_value
        
        # Add ambiguity indicator
        row["Has Ambiguities"] = len(inv.get("other_options", {})) > 0
        rows.append(row)
    
    df = pd.DataFrame(rows)
    filepath = f"exports/{filename}"
    os.makedirs("exports", exist_ok=True)
    df.to_excel(filepath, index=False)
    return filepath

def export_to_json(invoices: List[Dict], filename: str = None) -> str:
    """Export individual invoices to JSON format"""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"invoice_details_{timestamp}.json"
    
    # Clean up invoices for export (remove internal fields)
    clean_invoices = []
    for inv in invoices:
        clean_inv = {k: v for k, v in inv.items() if not k.startswith("__")}
        clean_invoices.append(clean_inv)
    
    filepath = f"exports/{filename}"
    os.makedirs("exports", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(clean_invoices, f, indent=2, ensure_ascii=False)
    return filepath

# ── Navigation Component ─────────────────────────────────────
def render_navigation():
    """Render the navigation bar for processed invoices"""
    if "invoices" in st.session_state and len(st.session_state.invoices) > 0:
        st.markdown("""
        <div class="nav-container">
            <div class="nav-title">📊 Navigation • {} invoice{} processed</div>
        </div>
        """.format(len(st.session_state.invoices), "s" if len(st.session_state.invoices) > 1 else ""), unsafe_allow_html=True)
        
        nav_col1, nav_col2, nav_col3, nav_col4 = st.columns([1, 1, 1, 1])
        
        with nav_col1:
            if st.button("📋 Review Mode", 
                        type="primary" if st.session_state.mode == "review" else "secondary",
                        use_container_width=True,
                        help="Review and edit extracted data"):
                st.session_state.mode = "review"
                st.rerun()
        
        with nav_col2:
            if st.button("📊 Summary View", 
                        type="primary" if st.session_state.mode == "summary" else "secondary",
                        use_container_width=True,
                        help="View all invoices in a table"):
                st.session_state.mode = "summary"
                st.rerun()
        
        with nav_col3:
            if st.button("⚙️ Fields Config", 
                        type="primary" if st.session_state.mode == "config" else "secondary",
                        use_container_width=True,
                        help="Configure extraction fields"):
                st.session_state.mode = "config"
                st.rerun()
        
        with nav_col4:
            if st.button("🔄 New Upload",
                        type="secondary",
                        use_container_width=True,
                        help="Start over with new invoices"):
                st.session_state.clear()
                st.rerun()
    else:
        # Compact navigation for configuration mode when no invoices
        if st.session_state.mode == "config":
            st.markdown("""
            <div class="nav-container">
                <div class="nav-title">⚙️ Field Configuration</div>
            </div>
            """, unsafe_allow_html=True)
            
            nav_col1, nav_col2 = st.columns([1, 1])
            
            with nav_col1:
                if st.button("📤 Back to Upload", 
                            type="primary",
                            use_container_width=True):
                    st.session_state.mode = "upload"
                    st.rerun()
            
            with nav_col2:
                if st.button("🔄 New Session",
                            type="secondary",
                            use_container_width=True):
                    st.session_state.clear()
                    st.rerun()

# ── Mini Metric Component ─────────────────────────────────────
def mini_metric(label: str, val: str, width: int = 100):
    st.markdown(f"""
    <div style="
        display: inline-block;
        width: {width}px;
        text-align: center;
        margin-right: 1rem;
        vertical-align: middle;
        background-color: white;
        padding: 0.5rem;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
    ">
        <div style="font-size:0.9rem; color:#666; margin-bottom:0.2rem;">
            {label}
        </div>
        <div style="font-size:1.1rem; font-weight:bold; color:#333;">
            {val}
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Session State Initialization ──────────────────────────────
if "mode" not in st.session_state:
    st.session_state.mode = "upload"
if "idx" not in st.session_state:
    st.session_state.idx = 0
if "active_fields" not in st.session_state:
    st.session_state.active_fields = None



# ── MAIN CONTENT SECTIONS ─────────────────────────────────────
if st.session_state.mode == "upload":
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # ── Header ─────────────────────────────────────────────────────
        st.markdown("""
        <div class="main-header">
            <h1>📄 Invoice OCR Demo</h1>
            <p style="font-size: 1.2rem; margin-bottom: 0;">
                AI-Powered Invoice Processing | Part of Moeed's Portfolio
            </p>
            <p style="font-size: 1rem; opacity: 0.9;">
                Powered by Gen AI
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="info-card">
            <h3>🚀 About This Demo</h3>
            <p>This invoice OCR system demonstrates advanced AI capabilities for automated document processing:</p>
            <ul>
                <li><strong>Multi-format Support:</strong> PDF, JPG, PNG files</li>
                <li><strong>Smart Extraction:</strong> 12+ key invoice fields</li>
                <li><strong>Ambiguity Detection:</strong> Identifies uncertain values</li>
                <li><strong>Export Options:</strong> Excel summary & JSON details</li>
                <li><strong>Review Interface:</strong> Manual verification & correction</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

# ── Configuration Option for Upload Mode ─────────────────────
if "invoices" not in st.session_state or len(st.session_state.invoices) == 0:
    # Show field config option when no invoices are processed
    if st.session_state.mode == "upload":
        config_col1, config_col2 = st.columns([1, 4])
        with config_col1:
            if st.button("⚙️ Configure Fields"):
                st.session_state.mode = "config"
                st.rerun()

# ── FIELD CONFIGURATION MODE ─────────────────────────────────
if st.session_state.mode == "config":
    render_navigation()
    render_field_config_page()

# ── FILE UPLOADER ─────────────────────────────────────────────
elif st.session_state.mode == "upload":
    st.markdown("### ⚙️ Field Configuration")
    
    # Field selection
    selected_fields = get_preset_selector()
    
    if selected_fields:
        st.session_state.active_fields = selected_fields
        
        # Show selected fields preview
        field_manager = get_field_manager()
        active_field_defs = field_manager.get_active_fields(selected_fields)
        
        with st.expander(f"📋 Selected Fields ({len(selected_fields)})", expanded=False):
            for field_name in selected_fields:
                if field_name in active_field_defs:
                    field = active_field_defs[field_name]
                    required_badge = "🔴" if field.required else "⚪"
                    st.write(f"{required_badge} **{field.label}** - {field.description}")
    
    st.markdown("---")
    st.markdown("### 📤 Upload Invoice Files")
    
    uploaded = st.file_uploader(
        "Drag & drop invoices here (PDF/JPG/PNG)",
        type=['pdf', 'jpg', 'jpeg', 'png'],
        accept_multiple_files=True,
        help="Upload one or more invoice files for AI processing"
    )
    
    if uploaded:
        st.session_state.idx = 0
        os.makedirs("uploads", exist_ok=True)
        paths: List[str] = []
        
        # Save uploaded files
        for f in uploaded:
            dst = os.path.join("uploads", f.name)
            with open(dst, "wb") as out:
                out.write(f.getbuffer())
            paths.append(dst)
        
        # Process with progress indication
        progress_container = st.container()
        with progress_container:
            st.markdown("### 🔄 Processing Invoices...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            if lottie_anim:
                lottie_col1, lottie_col2, lottie_col3 = st.columns([1, 2, 1])
                with lottie_col2:
                    st_lottie(lottie_anim, height=200)
            
            t0 = time.time()
            
            # Simulate progress updates
            for i in range(101):
                progress_bar.progress(i)
                if i < 30:
                    status_text.text("🔍 Converting PDFs to images...")
                elif i < 60:
                    status_text.text("🤖 Running AI extraction...")
                elif i < 90:
                    status_text.text("✅ Verifying results...")
                else:
                    status_text.text("🎯 Finalizing processing...")
                time.sleep(0.02)
            
            # Actual processing with error handling
            try:
                # Debug: Test API connection first
                try:
                    test_response = model.generate_content("Test")
                    st.success("✅ API connection working")
                except Exception as api_error:
                    st.error(f"❌ API connection failed: {str(api_error)}")
                    st.stop()
                
                # Debug: Show file info
                st.info(f"📁 Processing {len(paths)} files:")
                for i, path in enumerate(paths):
                    st.write(f"  {i+1}. {Path(path).name} ({Path(path).suffix})")
                
                # Create a container to capture debug output
                debug_container = st.expander("🔍 Debug Output", expanded=True)
                
                # Capture debug output by redirecting stdout temporarily
                import sys
                from io import StringIO
                
                old_stdout = sys.stdout
                sys.stdout = debug_buffer = StringIO()
                
                try:
                    active_fields_tuple = tuple(st.session_state.active_fields) if st.session_state.active_fields else None
                    st.session_state.invoices = load_invoices(model, tuple(paths), active_fields_tuple)
                    st.session_state.processing_time = time.time() - t0
                finally:
                    # Restore stdout and display debug output
                    sys.stdout = old_stdout
                    debug_output = debug_buffer.getvalue()
                    
                    if debug_output:
                        with debug_container:
                            st.code(debug_output, language="text")
                
                # Check if processing returned any results
                if not st.session_state.invoices:
                    st.error("❌ Processing failed: No invoices could be extracted from the uploaded files.")
                    st.markdown("""
                    **Possible reasons:**
                    - Files may not contain valid invoices
                    - API key issues
                    - Image quality too low
                    - Unsupported file format or corruption
                    """)
                    st.stop()
                    
            except Exception as e:
                st.error(f"❌ Processing error: {str(e)}")
                st.markdown("Please check your API key configuration and try again.")
                st.stop()
            
        progress_container.empty()
        
        # Process images and set mode
        os.makedirs("processed_images", exist_ok=True)
        for inv in st.session_state.invoices:
            src_img = inv["__image_path"]
            dst_img = os.path.join("processed_images", Path(src_img).name)
            if src_img != dst_img:
                import shutil
                shutil.copy(src_img, dst_img)
                inv["__image_path"] = dst_img
        
        st.session_state.mode = "review"
        st.success(f"✅ Successfully processed {len(st.session_state.invoices)} invoice(s)!")
        st.rerun()

# ── SUMMARY VIEW ───────────────────────────────────────────────
elif st.session_state.mode == "summary" and "invoices" in st.session_state:
    st.markdown("### 📊 Invoice Summary")
    render_navigation()
    
    # Export buttons
    export_col1, export_col2, export_col3 = st.columns([2, 2, 4])
    
    with export_col1:
        if st.button("📄 Export to Excel"):
            excel_path = export_to_excel(st.session_state.invoices)
            with open(excel_path, "rb") as f:
                st.download_button(
                    label="⬇️ Download Excel",
                    data=f.read(),
                    file_name=Path(excel_path).name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    
    with export_col2:
        if st.button("🔧 Export to JSON"):
            json_path = export_to_json(st.session_state.invoices)
            with open(json_path, "r", encoding="utf-8") as f:
                st.download_button(
                    label="⬇️ Download JSON",
                    data=f.read(),
                    file_name=Path(json_path).name,
                    mime="application/json"
                )
    
    # Summary statistics
    total_amount = 0
    ambiguous_count = 0
    for inv in st.session_state.invoices:
        amount_str = str(inv.get("total_invoice_amount", "0"))
        amount = float(''.join(filter(str.isdigit, amount_str))) if amount_str else 0
        total_amount += amount
        if len(inv.get("other_options", {})) > 0:
            ambiguous_count += 1
    
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    with stat_col1:
        st.metric("Total Invoices", len(st.session_state.invoices))
    with stat_col2:
        st.metric("Total Amount", f"₹{total_amount:,.0f}")
    with stat_col3:
        st.metric("Ambiguous Items", ambiguous_count)
    with stat_col4:
        pt = st.session_state.processing_time
        st.metric("Processing Time", f"{int(pt//60)}m {pt%60:.1f}s")
    
    # Data grid with dynamic fields
    field_manager = get_field_manager()
    all_fields = field_manager.get_all_fields()
    
    rows = []
    for inv in st.session_state.invoices:
        row = {}
        
        # Add all non-internal fields
        for key, value in inv.items():
            if key.startswith("__") or key == "other_options":
                continue
                
            # Get field label if available
            if key in all_fields:
                label = all_fields[key].label
            else:
                # Create short label for display
                label = key.replace("_", " ").title()
                if len(label) > 15:
                    label = label[:12] + "..."
            
            # Format value based on type
            if isinstance(value, list):
                formatted_value = ", ".join(str(x) for x in value)
            else:
                formatted_value = str(value) if value else ""
                
            row[label] = formatted_value
        
        # Add ambiguity indicator
        row["Ambiguous?"] = "Yes" if len(inv.get("other_options", {})) > 0 else "No"
        rows.append(row)
    
    df = pd.DataFrame(rows)
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        filter="agSetColumnFilter",
        sortable=True,
        resizable=True
    )
    gridOptions = gb.build()
    
    AgGrid(
        df,
        gridOptions=gridOptions,
        theme="alpine",
        enable_enterprise_modules=True,
        allow_unsafe_jscode=True,
        update_mode=GridUpdateMode.NO_UPDATE,
        height=400,
        fit_columns_on_grid_load=True
    )

# ── REVIEW VIEW ────────────────────────────────────────────────
elif st.session_state.mode == "review" and "invoices" in st.session_state:
    invoices = st.session_state.invoices
    total = len(invoices)
    
    # Handle empty invoice list or invalid index
    if not invoices or total == 0:
        st.error("⚠️ No invoices were processed successfully. This could be due to:")
        st.markdown("""
        - Invalid or corrupted image files
        - Images that don't contain invoices
        - API key issues
        - Network connectivity problems
        
        Please try uploading different invoice files.
        """)
        st.session_state.mode = "upload"
        if st.button("🔄 Try Again"):
            st.rerun()
        st.stop()
    
    idx = st.session_state.idx
    
    # Ensure index is within bounds
    if idx >= total or idx < 0:
        st.session_state.idx = 0
        idx = 0
    
    inv = invoices[idx]
    img_path = inv["__image_path"]
    
    # ── TOP TOOLBAR ────────────────────────────────────────────
    st.markdown("### 🔍 Invoice Review")
    render_navigation()
    
    left, right = st.columns([6, 4])
    with left:
        navcol, titlecol, a, b, c = st.columns([0.5, 1, 1, 1, 1])
        with titlecol:
            st.markdown(f"**Invoice {idx+1} of {total}**")
            st.progress((idx+1)/total)
        with a:
            mini_metric("Processed", f"{idx+1}/{total}")
        with b:
            mini_metric("Ambiguous", str(len(inv.get("other_options", {}))))
        with c:
            pt = st.session_state.processing_time
            mini_metric("Time", f"{int(pt//60)}m {pt%60:.1f}s")
    
    with right:
        b1, b2, b3, b4 = st.columns([1, 1, 1, 1])
        with b1:
            st.button("⬅️ Prev", 
                     disabled=(idx == 0),
                     on_click=lambda: st.session_state.__setitem__('idx', idx-1))
        with b2:
            st.button("Next ➡️", 
                     disabled=(idx >= total-1),
                     on_click=lambda: st.session_state.__setitem__('idx', idx+1))
        with b3:
            st.button("🏠 Home", 
                     on_click=lambda: st.session_state.__setitem__('idx', 0))
        with b4:
            st.button("🔄 Reset", 
                     on_click=lambda: st.session_state.clear())
    
    # ── MAIN CONTENT ────────────────────────────────────────────
    left_col, center_col, right_col = st.columns([2, 3, 2], gap="large")
    
    with left_col:
        st.subheader("📋 Extracted Data")
        
        # Render extracted fields with dynamic labels
        field_manager = get_field_manager()
        all_fields = field_manager.get_all_fields()
        
        other_opts = inv.get("other_options", {}) or {}
        
        # Debug: Show other_options structure
        st.write("🔍 Debug - other_options found:", len(other_opts), "fields")
        if other_opts:
            st.write("🔍 Debug - other_options:", other_opts)
        else:
            st.write("🔍 Debug - No other_options in invoice data")
            
        # Debug: Show full invoice structure (excluding image path)
        debug_inv = {k: v for k, v in inv.items() if not k.startswith("__")}
        st.write("🔍 Debug - Full invoice data:", debug_inv)
        
        edits: Dict[str, str] = {}
        
        for fld, val in inv.items():
            if fld.startswith("__") or fld == "other_options":
                continue
            
            # Get proper field label
            if fld in all_fields:
                label = all_fields[fld].label
            else:
                label = fld.replace("_", " ").title()
                
            default = str(val) if val else ""
            
            if fld in other_opts:
                raw = other_opts[fld]["options"]
                if raw and isinstance(raw[0], dict):
                    choices = [o["option"] for o in raw]
                elif all(isinstance(o, list) and len(o) == 2 for o in raw):
                    choices = [o[0] for o in raw]
                else:
                    choices = [str(raw[i]) for i in range(0, len(raw), 2)]
                choices.append("Other…")
                
                sel = st.selectbox(
                    label,
                    choices,
                    index=choices.index(default) if default in choices else len(choices)-1,
                    key=f"select_{fld}_{idx}"
                )
                new = sel if sel != "Other…" else (
                    st.text_input(f"{label} (Custom)", placeholder=default, key=f"input_{fld}_{idx}") or default
                )
            else:
                new = st.text_input(label, value=default, disabled=True, key=f"field_{fld}_{idx}")
            
            edits[fld] = new
        
        inv.update(edits)
    
    with center_col:
        st.subheader(f"📄 {Path(img_path).name}")
        if os.path.exists(img_path):
            st.image(Image.open(img_path), use_container_width=True)
        else:
            st.error("Image file not found")
    
    with right_col:
        st.subheader("⚠️ Ambiguities")
        opts = inv.get("other_options", {})
        if opts:
            for f, detail in opts.items():
                st.markdown(f"**{f.replace('_', ' ').title()}**")
                for o in detail["options"]:
                    if isinstance(o, dict):
                        st.write(f"- {o['option']} ({o['score']}%)")
                    elif isinstance(o, list) and len(o) == 2:
                        st.write(f"- {o[0]} ({o[1]}%)")
                    else:
                        st.write(f"- {o}")
                if detail.get("reason"):
                    st.info(detail["reason"])
        else:
            st.success("No ambiguities detected!")

# ── Footer ─────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    <p><strong>Invoice OCR Demo</strong></p>
    <p>Part of Moeed's Portfolio | Visit <a href="https://meetmoeed.com" target="_blank">meetmoeed.com</a></p>
</div>
""", unsafe_allow_html=True)