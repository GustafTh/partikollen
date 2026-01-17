import streamlit as st
import pandas as pd
import json
import os
import re
import requests
import time
import datetime
import math
import sys
import io
import hashlib
import google.generativeai as genai
from google.cloud import firestore
from google.oauth2 import service_account
from pypdf import PdfReader
import plotly.express as px

# Fixar teckenkodning och stora heltal
sys.stdout.reconfigure(encoding='utf-8')
sys.set_int_max_str_digits(0)

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Partikollen Dashboard", page_icon="🏛️", layout="wide")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("Ingen Google API-nyckel hittades.")
    st.stop()

if "FIREBASE_KEY" in st.secrets:
    try:
        key_input = st.secrets["FIREBASE_KEY"]
        key_dict = json.loads(key_input) if isinstance(key_input, str) else key_input
        creds = service_account.Credentials.from_service_account_info(key_dict)
        db = firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"Databasfel: {e}")
        st.stop()
else:
    st.warning("⚠️ Ingen databasnyckel.")
    st.stop()

# --- 2. HJÄLPFUNKTIONER ---
def stada_text(text):
    if not text: return ""
    text = text.replace("<p>", "\n\n").replace("<br>", "\n").replace("</p>", "")
    text = text.replace("<li>", "\n- ").replace("</li>", "")
    text = text.replace("<b>", "**").replace("</b>", "**")
    text = re.sub(r'<[^<]+?>', '', text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("HTML", "")
    text = text.replace("Dokumentet är inte publicerat", "")
    return re.sub(r'\n\s*\n', '\n\n', text).strip()

def hamta_pdf_text(url):
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            with io.BytesIO(resp.content) as f:
                reader = PdfReader(f)
                full_text = ""
                for page in reader.pages:
                    full_text += page.extract_text() + "\n"
                return stada_text(full_text)
    except: return ""
    return ""

def hamta_full_text(doc_dict):
    texten = doc_dict.get('full_text', '')
    if doc_dict.get('is_chunked'):
        try:
            parts_ref = db.collection("riksdagen_docs").document(doc_dict['dok_id']).collection('text_parts')
            parts = parts_ref.stream()
            sorted_parts = sorted([p.to_dict() for p in parts], key=lambda x: x['index'])
            for part in sorted_parts:
                texten += part.get('text_part', '')
        except Exception: pass
    return texten

def hitta_parti(dok, doktyp):
    if doktyp == 'bet': return "Utskottet"
    if doktyp == 'prop': return "Regeringen"
    if dok.get('parti') and dok.get('parti') != "-": return dok['parti'].upper()
    return "-"

def spara_till_db_smart(post):
    MAX_BYTES = 900000
    doc_ref = db.collection("riksdagen_docs").document(post['dok_id'])
    texten = post.get('full_text', '')
    if len(texten.encode('utf-8')) < MAX_BYTES:
        doc_ref.set(post)
        return
    chunks = [texten[i:i+MAX_BYTES] for i in range(0, len(texten), MAX_BYTES)]
    post['full_text'] = chunks[0]
    post['is_chunked'] = True
    doc_ref.set(post)
    for i, chunk in enumerate(chunks[1:], start=1):
        doc_ref.collection('text_parts').document(str(i)).set({
            'index': i, 'text_part': chunk, 'parent_id': post['dok_id']
        })

# --- MINNES- & AI-FUNKTIONER ---
def skapa_hash(text):
    return hashlib.md5(text.lower().strip().encode()).hexdigest()

def hitta_sparad_analys(fraga):
    fraga_id = skapa_hash(fraga)
    doc = db.collection("analyser").document(fraga_id).get()
    if doc.exists: return doc.to_dict()
    return None

def spara_analys(fraga, svar, kod=""):
    fraga_id = skapa_hash(fraga)
    data = {
        "fraga": fraga, "svar": svar, "kod": kod,
        "datum": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    db.collection("analyser").document(fraga_id).set(data)

def kor_ai_analys(full_prompt):
    """Försöker med bästa modellen först, faller tillbaka på stabil om det krånglar."""
    modeller_att_testa = ["gemini-1.5-pro-latest", "gemini-1.5-pro", "gemini-pro"]
    
    for modell_namn in modeller_att_testa:
        try:
            model = genai.GenerativeModel(modell_namn)
            response = model.generate_content(full_prompt)
            return response.text, modell_namn # Returnera svar + vilken modell som funkade
        except Exception as e:
            # Om det är sista modellen och det fortfarande inte funkar, kasta felet
            if modell_namn == modeller_att_testa[-1]:
                raise e
            continue # Annars, testa nästa i listan
    return None, None

@st.cache_data(ttl=600)
def ladda_index():
    docs_list = []
    try:
        docs = db.collection("riksdagen_docs").select(['dok_id', 'titel', 'parti', 'datum', 'Kategori', 'full_text', 'web_url', 'pdf_url', 'beslut']).stream()
        for doc in docs:
            d = doc.to_dict()
            d['dok_id'] = doc.id
            docs_list.append(d)
    except Exception: return pd.DataFrame()
    if not docs_list: return pd.DataFrame()
    df = pd.DataFrame(docs_list)
    if "datum" in df.columns: df["datum"] = pd.to_datetime(df["datum"], errors='coerce')
    return df

# --- 3. UI ---
with st.sidebar:
    st.header("⚙️ Inställningar")
    idag = datetime.date.today()
    start_datum = st.date_input("Hämta från:", idag - datetime.timedelta(days=30))
    slut_datum = st.date_input("Till:", idag)
    st.info("💡 Filtret ovan styr bara nyinhämtning. AI:n och Utforskaren ser allt i databasen.")

st.title("🏛️ Partikollen Cloud ☁️")
tab1, tab2, tab3 = st.tabs(["📡 Inhämtning", "🔍 Utforskaren", "🧠 AI-Analys (Hela databasen)"])

# === FLIK 1: INHÄMTNING ===
with tab1:
    st.header("Hämta ny data")
    c1, c2 = st.columns(2)
    with c1:
        check_mot = st.checkbox("Motioner & Prop", value=True)
        check_beslut = st.checkbox("Beslut", value=True)
        max_sidor = st.number_input("Sidor:", 1, 100, 3)
        btn_run = st.button("🚀 Starta", type="primary")

    if btn_run:
        status = st.status("Jobbar...", expanded=True)
        from_str, tom_str = start_datum.strftime("%Y-%m-%d"), slut_datum.strftime("%Y-%m-%d")

        def kor_jobb(doktyp, label):
            status.write(f"Hämtar {label}...")
            count = 0
            for p in range(1, max_sidor + 1):
                url = f"https://data.riksdagen.se/dokumentlista/?doktyp={doktyp}&sz=20&p={p}&from={from_str}&tom={tom_str}&utformat=json"
                try:
                    data = requests.get(url).json()
                    docs = data.get('dokumentlista', {}).get('dokument', [])
                    if not docs: break
                    if isinstance(docs, dict): docs = [docs]

                    for d in docs:
                        did = d['dok_id']
                        saker_web = f"https://www.riksdagen.se/dokument/{did}"
                        saker_pdf = f"https://data.riksdagen.se/fil/{did}"
                        ren_text, kalla = "", "HTML"
                        
                        try:
                            h = requests.get(f"https://data.riksdagen.se/dokument/{did}.html")
                            if h.status_code == 200: ren_text = stada_text(h.text)
                        except: pass
                        
                        if len(ren_text) < 300 or "inte publicerat" in ren_text:
                            status.write(f"📄 PDF: {did}")
                            pdf_txt = hamta_pdf_text(saker_pdf)
                            if len(pdf_txt) > len(ren_text): ren_text, kalla = pdf_txt, "PDF"
                        
                        if ren_text:
                            typ_map = {"mot": "Motion", "prop": "Proposition", "bet": "Beslut"}
                            post = {
                                'dok_id': did, 'titel': d['titel'], 'datum': d['datum'],
                                'full_text': ren_text, 'typ': doktyp, 
                                'Kategori': typ_map.get(doktyp, "Övrigt"),
                                'parti': hitta_parti(d, doktyp), 'Källa': kalla,
                                'web_url': saker_web, 'pdf_url': saker_pdf,
                                'beslut': d.get('beslut', '')
                            }
                            spara_till_db_smart(post)
                            count += 1
                            time.sleep(0.1)
                except Exception as e: status.warning(f"Fel sid {p}: {e}")
            return count

        tot = 0
        if check_mot: tot += kor_jobb("mot", "Motioner") + kor_jobb("prop", "Propositioner")
        if check_beslut: tot += kor_jobb("bet", "Beslut")
        status.success(f"Klar! Sparade {tot} st.")
        st.cache_data.clear()
        time.sleep(2)
        st.rerun()

# === FLIK 2: UTFORSKAREN ===
with tab2:
    if "valt_dok" not in st.session_state: st.session_state["valt_dok"] = None
    df = ladda_index()

    if st.session_state["valt_dok"]:
        doc = st.session_state["valt_dok"]
        if st.button("⬅️ Tillbaka"): 
            st.session_state["valt_dok"] = None
            st.rerun()
        
        st.title(doc['titel'])
        st.caption(f"📅 {doc['datum']} | 🏛️ {doc['parti']} | ID: {doc['dok_id']}")
        c1, c2 = st.columns([1, 1])
        c1.link_button("🌐 Webb", doc.get('web_url', '#'), use_container_width=True)
        c2.link_button("📥 PDF", doc.get('pdf_url', '#'), use_container_width=True)
        st.divider()
        with st.spinner("Laddar text..."):
            full_txt = hamta_full_text(doc)
            st.markdown(full_txt if full_txt else "Ingen text hittades.")

    elif not df.empty:
        sok = st.text_input("🔍 Sök i listan:", placeholder="Filtrera visningen...")
        v_df = df.copy()
        if sok:
            v_df = v_df[v_df['titel'].str.contains(sok, case=False, na=False) | v_df['full_text'].str.contains(sok, case=False, na=False)]
        
        for _, r in v_df.head(20).iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([5, 1])
                c1.subheader(r['titel'])
                c1.caption(f"{r['Kategori']} | {r['parti']} | {r['datum'].date()}")
                if r['full_text']: c1.markdown(f"*{r['full_text'][:140]}...*")
                if c2.button("Läs", key=r['dok_id'], use_container_width=True):
                    st.session_state["valt_dok"] = r.to_dict()
                    st.rerun()

# === FLIK 3: AI-CHATT ===
with tab3:
    st.header("🧠 Analysera hela databasen")
    st.caption("AI:n väljer automatiskt den bästa tillgängliga modellen.")
    
    tvinga_ny = st.checkbox("🔄 Tvinga ny analys (Ignorera minnet)")
    df_all = ladda_index()
    
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hej! Vad vill du veta om riksdagsdatan?"}]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Skriv din fråga här..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            sparad = hitta_sparad_analys(prompt)
            
            if sparad and not tvinga_ny:
                st.info(f"💡 Hämtade sparat svar från {sparad['datum']}")
                st.markdown(sparad['svar'])
                st.session_state.messages.append({"role": "assistant", "content": sparad['svar']})
                if sparad.get('kod'):
                    try:
                        meta_df = df_all[['dok_id', 'titel', 'parti', 'datum', 'Kategori', 'beslut']].copy()
                        local_env = {"meta_df": meta_df, "pd": pd, "px": px}
                        exec(sparad['kod'], {}, local_env)