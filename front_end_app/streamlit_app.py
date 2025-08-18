import os
import time
from pathlib import Path
from typing import List, Dict
from urllib.parse import quote_plus
import shutil

import pandas as pd
import requests
import streamlit as st           # ← STREAMLIT IMPORT
from PIL import Image
from dateutil import parser
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai import GenerationConfig
from sqlalchemy import create_engine, text
import oracledb


# ── Page Config ────────────────────────────────────────────────
st.set_page_config(page_title="Invoice Automation System", layout="wide")

def init_oracle():
    oracledb.init_oracle_client(lib_dir=r"C:\instantclient_21_13")
    dsn = oracledb.makedsn("10.0.25.109", 1521, service_name="PROD")
    return oracledb.connect(
        user="IL267683",
        password="Abc_123",
        dsn=dsn
    )

# Initialize Oracle connection
oracle_conn = init_oracle()

from streamlit_lottie import st_lottie
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from ocr_pipeline import (
    batch_convert_pdfs_to_images,
    ocr_financial_document,
    verify_financial_extraction,
    enrich_with_other_options,
    process_invoices_as_docs
)

# ── App Title ─────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.title("📄 Invoice Automation System")

# ── STATIC CREDENTIALS ─────────────────────────────────────────
_CREDENTIALS = {
    "1WPSDT":        "14166",
    "WJAVAID":       "4089",
    "SMDIN":         "1701",
    "RASHIDN":       "1123",
    "NABILA.MAJEED": "10382",
}
_PASSWORD = "Pass123"

# ── Session defaults ───────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user = None

# ── Login screen ───────────────────────────────────────────────
if not st.session_state.authenticated:
    st.title("🔒 Login")
    user = st.text_input("Username")
    pwd  = st.text_input("Password", type="password")
    if st.button("Log in"):
        if user in _CREDENTIALS and pwd == _PASSWORD:
            st.session_state.authenticated = True
            st.session_state.user = {
                "username": user,
                "userID":   _CREDENTIALS[user]
            }
            st.rerun()
        else:
            st.error("❌ Invalid username or password")
    st.stop()

# ── Logged-in header ───────────────────────────────────────────
if st.session_state.authenticated:
    col1, col2, col3 = st.columns([8, 1, 1])
    with col1:
        st.title("📄 Invoice Automation System")
    with col2:
        st.markdown(f"**Logged in as:** {st.session_state.user['username']}")
    with col3:
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.session_state.user = None
            st.rerun()
    col5, col6 = st.columns([1, 1])
    with col5:
        st.write("")
    with col6:
        st.write("")

# ── GLOBAL STYLE OVERRIDES ────────────────────────────────────
st.markdown(
    """
    <style>
      /* toolbar background */
      [data-testid="stBlockContainer"] > div:nth-child(2) {
        background-color: #B7D0F8 !important;
        padding: 0.75rem 1rem !important;
        border-radius: 0.5rem !important;
        margin-bottom: 1rem !important;
      }
      /* labels */
      label {
        font-size: 18px !important;
        font-weight: 700 !important;
        color: #000 !important;
      }
      /* disabled inputs */
      input[disabled], textarea[disabled] {
        background-color: #eeeeee !important;
        color: #000000 !important;
      }
      /* app background */
      [data-testid="stAppViewContainer"] {
        background-color: #f8f7ff !important;
      }
      /* card background */
      [data-testid="stBlockContainer"] {
        background-color: #FFFFFF !important;
      }
      /* shrink built-in metric numbers */
      [data-testid="metric-container"] div[class*="value"] {
        font-size: 0.3rem !important;
        line-height: 0.8rem !important;
      }
      /* tighten buttons */
      .stButton>button {
        white-space: nowrap !important;
        font-size: 0.8rem !important;
        padding: 0.3rem 0.6rem !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Environment & DB Setup ─────────────────────────────────────
load_dotenv()
SQL_SERVER   = os.getenv("SQL_SERVER",   "10.0.12.30")
SQL_PORT     = os.getenv("SQL_PORT",     "1433")
SQL_DATABASE = os.getenv("SQL_DATABASE", "ndb")
SQL_USERNAME = os.getenv("SQL_USERNAME", "ds_login")
SQL_PASSWORD = os.getenv("SQL_PASSWORD", "ds_login_789")

conn_str = (
    f"mssql+pyodbc://{SQL_USERNAME}:{quote_plus(SQL_PASSWORD)}"
    f"@{SQL_SERVER},{SQL_PORT}/{SQL_DATABASE}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
)
engine = create_engine(conn_str, fast_executemany=True)

def save_invoice_to_db(inv: dict, file_url: str, vendor_id: str, vendor_name: str):
    """
    Save the invoice to Oracle STG_DT_INVOICES table, reconnecting each time
    to ensure a live session.
    """
    conn = init_oracle()

    raw_date = inv.get("invoice_date")
    try:
        date_val = parser.parse(raw_date, dayfirst=True).date()
    except:
        date_val = None

    raw_po = inv.get("po_numbers") or []
    if isinstance(raw_po, list):
        po_str = ",".join(str(x) for x in raw_po)
    else:
        po_str = str(raw_po).strip('"\'')
    
    created_by = st.session_state.user["userID"]

    with conn.cursor() as cur:
        cur.execute("SELECT aff.GRN_TRAN_SEQ.nextval FROM SYS.dual")
        tran_id = cur.fetchone()[0]

    sql = """INSERT INTO AFF.STG_DT_INVOICES (
            INVOICEID, INVOICETYPE, BUYERNAME,
            VENDORID, VENDORNAME, INVOICEDATE,
            TOTALINVOICEAMOUNT, CURRENCY, PONUMBERS,
            DELIVERYCHALLANNUMBER, ATTACHMENT_URL,
            CREATED_BY, TRAN_ID
        ) VALUES (
            :1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13
        )"""

    values = [
        inv.get("invoice_number"), inv.get("invoice_type"), inv.get("buyer_name"),
        vendor_id, vendor_name, date_val,
        inv.get("total_invoice_amount"), inv.get("currency"),
        po_str, inv.get("delivery_challan_number"), file_url,
        created_by, tran_id
    ]

    with conn.cursor() as cur:
        cur.execute(sql, values)
        conn.commit()

def mini_metric(label: str, val: str, width: int = 80):
    st.markdown(
        f"""
        <div style="
            display: inline-block;
            width: {width}px;
            text-align: center;
            margin-right: 1rem;
            vertical-align: middle;
        ">
          <div style="font-size:1rem; color:#555; margin-bottom:0.1rem;">
            {label}
          </div>
          <div style="font-size:1.2rem; font-weight:bold; line-height:1;">
            {val}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Load & Cache the Generative Model ─────────────────────────
os.environ["GOOGLE_CLOUD_PROJECT"] = "354506728158"
@st.cache_resource
def load_model():
    api_key = "AIzaSyC90nXGzSxx1MlzM4TBgFtwdA8EhQo_oU4"
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        "gemini-2.5-pro",
        generation_config=GenerationConfig(temperature=1.8)
    )
model = load_model()

# ── Lottie Loader ─────────────────────────────────────────────
@st.cache_data
def load_lottie_url(url: str):
    r = requests.get(url)
    return r.json() if r.status_code == 200 else None

lottie_anim = load_lottie_url(
    "https://lottie.host/fda0e746-60d5-4120-a918-c79c128b1bef/Ip6YQwzhGA.json"
)

# ── Invoice Pipeline (cached) ─────────────────────────────────
@st.cache_data(show_spinner=False)
def load_invoices(_model, paths: tuple) -> list:
    return process_invoices_as_docs(_model, list(paths))

# ── Mode toggle ───────────────────────────────────────────────
mode = st.session_state.get("mode", "review")

# ── FILE UPLOADER ─────────────────────────────────────────────
if mode == "review" and "invoices" not in st.session_state:
    uploader_ph = st.empty()
    uploaded = uploader_ph.file_uploader(
        "Drag & drop invoices here (PDF/JPG/PNG)",
        type=['pdf', 'jpg', 'jpeg', 'png'],
        accept_multiple_files=True
    )
    if uploaded:
        uploader_ph.empty()
        st.session_state.idx = 0
        os.makedirs("uploads", exist_ok=True)
        paths: List[str] = []
        for f in uploaded:
            dst = os.path.join("uploads", f.name)
            with open(dst, "wb") as out:
                out.write(f.getbuffer())
            paths.append(dst)

        placeholder = st.empty()
        t0 = time.time()
        with placeholder.container():
            with st.spinner("Processing invoices..."):
                if lottie_anim:
                    st_lottie(lottie_anim, height=150)
                st.session_state.invoices = load_invoices(model, tuple(paths))
        placeholder.empty()
        st.session_state.processing_time = time.time() - t0

        # ── Save converted images into local + share subfolders by type ──
        LOCAL_BASE = "Invoices"
        SHARE_BASE = r"Invoices"
        os.makedirs(LOCAL_BASE, exist_ok=True)

        for inv in st.session_state.invoices:
            itype = inv.get("invoice_type", "Commercial")  # either "Commercial" or "Sales Tax"

            # 1) local folder
            local_dir = Path(LOCAL_BASE) / itype
            local_dir.mkdir(parents=True, exist_ok=True)
            src_img   = inv["__image_path"]
            dst_local = local_dir / Path(src_img).name
            shutil.copy(src_img, dst_local)
            inv["__local_path"] = str(dst_local)

            # 2) network‐share folder
            share_dir = Path(SHARE_BASE) / itype
            share_dir.mkdir(parents=True, exist_ok=True)
            dst_share = share_dir / Path(src_img).name
            shutil.copy(src_img, dst_share)
            inv["__share_path"] = str(dst_share)
            inv["__orig_supplier"] = inv.get("supplier_name", "")

# ── SUMMARY VIEW ───────────────────────────────────────────────
if mode == "summary" and "invoices" in st.session_state:
    rows = []
    for inv in st.session_state.invoices:
        raw_po = inv.get("po_numbers") or []
        if isinstance(raw_po, str):
            raw_po = [raw_po]
        po_str = ", ".join(str(x) for x in raw_po)
        rows.append({
            "Invoice Type":inv.get("invoice_type", ""), 
            "Invoice#":   inv.get("invoice_number", ""),
            "Buyer":      inv.get("buyer_name", ""),
            "Supplier":   inv.get("supplier_name", ""),
            "Date":       inv.get("invoice_date", ""),
            "Amount":     inv.get("total_invoice_amount", ""),
            "Currency":   inv.get("currency", ""),
            "POs":        po_str,
            "Challan#":   inv.get("delivery_challan_number", "") or "",
            "Ambiguous?": len(inv.get("other_options", {})) > 0
        })

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

    if st.button("↩️ Back to Review"):
        st.session_state.mode = "review"
        st.rerun()
    st.stop()

# ── REVIEW VIEW ────────────────────────────────────────────────
if mode == "review" and "invoices" in st.session_state:
    invoices = st.session_state.invoices
    total    = len(invoices)
    idx      = st.session_state.idx
    inv      = invoices[idx]
    img_path = inv["__image_path"]
    file_url = f"{inv['__share_path']}"

    # initialize session_state defaults...
    if "vendor_id" not in st.session_state:
        st.session_state.vendor_id = None
    if "vendor_name" not in st.session_state:
        st.session_state.vendor_name = ""

    # ── TOP TOOLBAR ────────────────────────────────────────────
    left, right = st.columns([6, 4])
    with left:
        navcol, titlecol, a, b, c = st.columns([0.5,1,1,1,1])
        with navcol:
            pass
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
        b1, b2, b3, b4, spacer, b5, spacer2, b6 = st.columns([1,1,1.1,1,0.45,1,0.07,1])
        with b1:
            st.button("⬅️ Prev",
                      disabled=(idx == 0),
                      on_click=lambda: st.session_state.__setitem__('idx', idx-1))
        with b2:
            st.button("Next ➡️",
                      disabled=(idx >= total-1),
                      on_click=lambda: st.session_state.__setitem__('idx', idx+1))
        with b3:
            if st.button("💾 Save"):
                with st.spinner("Saving…"):
                    save_invoice_to_db(
                        inv,
                        file_url,
                        st.session_state.vendor_id,
                        st.session_state.vendor_name
                    )
                st.success("Saved")
        with b4:
            if st.button("📊 Summary"):
                st.session_state.mode = "summary"
                st.rerun()
        with spacer:
            st.write("")
        with b5:
            st.button("🏠 Home",
                      on_click=lambda: st.session_state.__setitem__('idx', 0))
        with spacer2:
            st.write("")
        with b6:
            st.button("🔄 Reset",
                      on_click=lambda: (st.session_state.clear(), load_invoices.clear()))

    # ── MAIN CONTENT ────────────────────────────────────────────
    left_col, center_col, right_col = st.columns([2,3,2], gap="large")
    with left_col:
        st.subheader("Extracted Data")

        # 2) Supplier lookup: only DB names, skip dropdown if exactly one choice
        orig = inv.get("__orig_supplier", "").strip()
        upper_orig = orig.upper()

        # try exact match first
        with oracle_conn.cursor() as cur:
            cur.execute("""
                SELECT VENDOR_ID, VENDOR_NAME
                  FROM AP.AP_SUPPLIERS
                 WHERE UPPER(VENDOR_NAME) = :upper
            """, upper=upper_orig)
            rows = cur.fetchall()

        # fallback to fuzzy LIKE
        if not rows:
            with oracle_conn.cursor() as cur:
                cur.execute("""
                    SELECT VENDOR_ID, VENDOR_NAME
                      FROM AP.AP_SUPPLIERS
                     WHERE UPPER(VENDOR_NAME) LIKE :pat
                """, pat=f"%{upper_orig}%")
                rows = cur.fetchall()

        # build map and list of DB names
        vendor_map = {name: vid for vid, name in rows}
        db_names   = list(vendor_map.keys())

        # decide whether to show dropdown
        if len(db_names) > 1:
            selected = st.selectbox(
                "Select Supplier Name",
                db_names,
                key="supplier_name_select"
            )
        elif len(db_names) == 1:
            # exactly one DB hit → auto-select it, no dropdown
            selected = db_names[0]
        else:
            # no DB hits → keep the OCR value
            selected = orig

        # stash for save step
        st.session_state.vendor_id   = vendor_map.get(selected)
        st.session_state.vendor_name = selected

        # always show the final Supplier Name here
        st.text_input(
            "Supplier Name",
            value=selected,
            disabled=True
        )

        # 3) now render all your other extracted‐fields exactly as before
        other_opts = inv.get("other_options", {}) or {}
        edits: Dict[str, str] = {}
        for fld, val in inv.items():
            if fld in ("supplier_name","other_options","__image_path","__doc_stem","__share_path","__orig_supplier","__local_path"):
                continue
            label   = fld.replace("_"," ").title()
            default = str(val)
            if fld in other_opts:
                raw = other_opts[fld]["options"]
                if raw and isinstance(raw[0], dict):
                    choices = [o["option"] for o in raw]
                elif all(isinstance(o,list) and len(o)==2 for o in raw):
                    choices = [o[0] for o in raw]
                elif isinstance(raw[0],list) and len(raw[0])==2:
                    choices = raw[0]
                else:
                    choices = [str(raw[i]) for i in range(0,len(raw),2)]
                choices.append("Other…")
                sel = st.selectbox(
                    label,
                    choices,
                    index=choices.index(default) if default in choices else len(choices)-1
                )
                new = sel if sel!="Other…" else (
                    st.text_input(label, placeholder=default) or default
                )
            else:
                new = st.text_input(label, value=default, disabled=True)
            edits[fld] = new
        inv.update(edits)


    with center_col:
        st.subheader(f"{Path(img_path).name}")
        st.image(Image.open(img_path), use_container_width=True)

    with right_col:
        st.subheader("Ambiguities")
        opts = inv.get("other_options", {})
        if opts:
            for f, detail in opts.items():
                st.markdown(f"**{f.replace('_',' ').title()}**")
                for o in detail["options"]:
                    if isinstance(o, dict):
                        st.write(f"- {o['option']} ({o['score']}%)")
                    elif isinstance(o, list) and len(o)==2:
                        st.write(f"- {o[0]} ({o[1]}%)")
                    else:
                        st.write(f"- {o}")
                if detail.get("reason"):
                    st.info(detail["reason"])
        else:
            st.write("None!")

else:
    st.info("Upload one or more invoices to begin.")
