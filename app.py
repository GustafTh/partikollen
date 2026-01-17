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
from google import genai
from google.cloud import firestore
from google.oauth2 import service_account
from pypdf import PdfReader  # NYTT: För att läsa PDF:er

# Fixar teckenkodning och stora heltal
sys.stdout.reconfigure(encoding='utf-8')
sys.set_int_max_str_digits(0)

# --- 1. KONFIGURATION & DATABAS ---
st.set_page_config(page_title="Partikollen Dashboard", page_icon="🏛️", layout="wide")

if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
    client = genai.Client(api_key=API_KEY)
else:
    st.error("Ingen Google API-nyckel hittades.")
    st.stop()

if "FIREBASE_KEY" in st.secrets:
    try:
        key_input = st.secrets["FIREBASE_KEY"]
        key_dict = json.loads(key_input) if isinstance(key_input, str) else key_input
        creds = service_account.Credentials.from_service_account_info(key_dict)
        db = firestore.Client(credentials=creds, project=key_dict["project_id"])
        st.sidebar.success("✅ Molndatabas")
    except Exception as e:
        st.error(f"Databasfel: {e}")
        st.stop()
else:
    st.warning("⚠️ Ingen databasnyckel.")
    st.stop()

# --- 2. HJÄLPFUNKTIONER ---

def stada_text(text):
    if not text: return ""
    # Tar bort HTML-taggar och städar mellanslag
    text = re.sub(r'<[^<]+?>', ' ', text)
    text = text.replace("HTML", "").replace("Dokumentet är inte publicerat", "")
    return " ".join(text.split())

def hamta_pdf_text(dok_id):
    """Försöker ladda ner PDF och extrahera text om HTML saknas."""
    pdf_url = f"https://data.riksdagen.se/fil/{dok_id}"
    try:
        resp = requests.get(pdf_url, timeout=10)
        if resp.status_code == 200:
            # Läs PDF från minnet
            with io.BytesIO(resp.content) as f:
                reader = PdfReader(f)
                full_text = ""
                for page in reader.pages:
                    full_text += page.extract_text() + "\n"
                return stada_text(full_text)
    except Exception:
        return "" # Om det misslyckas, returnera tom sträng
    return ""

def hamta_full_text(doc_dict):
    """Hämtar ihopfogad text från chunks om det behövs."""
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
    """Sparar och chunkar om texten är för stor (PDF:er kan vara enorma)."""
    MAX_BYTES = 900000
    doc_ref = db.collection("riksdagen_docs").document(post['dok_id'])
    texten = post.get('full_text', '')
    
    # Om texten är liten, spara direkt
    if len(texten.encode('utf-8')) < MAX_BYTES:
        doc_ref.set(post)
        return
    
    # Om stor -> Chunka!
    chunks = [texten[i:i+MAX_BYTES] for i in range(0, len(texten), MAX_BYTES)]
    post['full_text'] = chunks[0]
    post['is_chunked'] = True
    doc_ref.set(post)
    
    for i, chunk in enumerate(chunks[1:], start=1):
        doc_ref.collection('text_parts').document(str(i)).set({
            'index': i, 'text_part': chunk, 'parent_id': post['dok_id']
        })

@st.cache_data(ttl=600)
def ladda_index():
    docs_list = []
    try:
        # Hämtar bara fälten vi behöver för listan för att spara bandbredd
        docs = db.collection("riksdagen_docs").select(['dok_id', 'titel', 'parti', 'datum', 'Kategori', 'full_text']).stream()
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
    st.header("⚙️ Filter")
    idag = datetime.date.today()
    start_datum = st.date_input("Från:", idag - datetime.timedelta(days=30))
    slut_datum = st.date_input("Till:", idag)

st.title("🏛️ Partikollen Cloud ☁️")
tab1, tab2, tab3 = st.tabs(["📡 Inhämtning", "🔍 Utforskaren", "🧠 AI-Analys"])

# === FLIK 1: INHÄMTNING (NU MED PDF-STÖD!) ===
with tab1:
    st.header("Hämta data (HTML + PDF)")
    st.info("Nu försöker appen läsa PDF-filen om den vanliga texten saknas.")
    
    c1, c2 = st.columns(2)
    with c1:
        check_mot = st.checkbox("Motioner & Prop", value=True)
        check_beslut = st.checkbox("Beslut (Betänkanden)", value=True)
        max_sidor = st.number_input("Sidor att söka:", 1, 100, 3)
        btn_run = st.button("🚀 Starta avancerad inhämtning", type="primary")

    if btn_run:
        status = st.status("Startar...", expanded=True)
        from_str, tom_str = start_datum.strftime("%Y-%m-%d"), slut_datum.strftime("%Y-%m-%d")

        def kor_jobb(doktyp, label):
            status.write(f"Söker {label}...")
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
                        
                        # 1. Försök hämta HTML-text
                        text_källa = "HTML"
                        ren_text = ""
                        h_resp = requests.get(f"https://data.riksdagen.se/dokument/{did}.html")
                        if h_resp.status_code == 200:
                            ren_text = stada_text(h_resp.text)
                        
                        # 2. Om texten är misstänkt kort eller "ej publicerad" -> Hämta PDF
                        if len(ren_text) < 200 or "inte publicerat" in h_resp.text:
                            status.write(f"📄 Hämtar PDF för {did}...")
                            pdf_text = hamta_pdf_text(did)
                            if len(pdf_text) > len(ren_text):
                                ren_text = pdf_text
                                text_källa = "PDF"
                        
                        # 3. Spara
                        if ren_text:
                            typ_map = {"mot": "Motion", "prop": "Proposition", "bet": "Beslut"}
                            post = {
                                'dok_id': did, 'titel': d['titel'], 'datum': d['datum'],
                                'full_text': ren_text, 'typ': doktyp, 
                                'Kategori': typ_map.get(doktyp, "Övrigt"),
                                'parti': hitta_parti(d, doktyp), 'Källa': text_källa
                            }
                            spara_till_db_smart(post)
                            count += 1
                            time.sleep(0.1)
                except Exception as e: status.warning(f"Fel på sida {p}: {e}")
            return count

        tot = 0
        if check_mot: tot += kor_jobb("mot", "Motioner") + kor_jobb("prop", "Propositioner")
        if check_beslut: tot += kor_jobb("bet", "Beslut")
        
        status.success(f"Klar! Sparade {tot} dokument (inklusive PDF-data).")
        st.cache_data.clear()
        time.sleep(2)
        st.rerun()

# === FLIK 2: UTFORSKAREN ===
with tab2:
    if "valt_dok" not in st.session_state: st.session_state["valt_dok"] = None
    df = ladda_index()

    if st.session_state["valt_dok"]:
        doc = st.session_state["valt_dok"]
        if st.button("⬅️ Lista"): 
            st.session_state["valt_dok"] = None
            st.rerun()
        
        st.subheader(doc['titel'])
        st.caption(f"ID: {doc['dok_id']} | Källa: {doc.get('Källa', 'Okänd')}")
        st.link_button("🔗 Öppna original (Riksdagen.se)", f"https://www.riksdagen.se/sv/dokument-och-lagar/dokument/_/{doc['dok_id']}")
        
        with st.spinner("Laddar text..."):
            full_txt = hamta_full_text(doc)
            st.text_area("Innehåll", full_txt, height=600)

    elif not df.empty:
        sok = st.text_input("Sök i text/titel:")
        filt_df = df[df['titel'].str.contains(sok, case=False, na=False) | df['full_text'].str.contains(sok, case=False, na=False)] if sok else df
        
        for _, r in filt_df.head(20).iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{r['titel']}** ({r['parti']})")
                c1.caption(f"{r['datum']} | {r['Kategori']}")
                if c2.button("Läs", key=r['dok_id']):
                    st.session_state["valt_dok"] = r.to_dict()
                    st.rerun()

# === FLIK 3: AI ===
with tab3:
    st.header("🧠 AI-Analys")
    if not df.empty:
        fraga = st.text_area("Fråga din data:", "Vad handlar de senaste motionerna om?")
        if st.button("Kör"):
            urval = df.head(10) # Tar de 10 senaste
            context = ""
            for _, r in urval.iterrows():
                context += f"\nDokument: {r['titel']}\nText: {r['full_text'][:1000]}...\n"
            
            try:
                res = client.models.generate_content(model="gemini-1.5-flash", contents=f"Svara på svenska.\nFråga: {fraga}\nData:\n{context}")
                st.markdown(res.text)
            except Exception as e: st.error(e)