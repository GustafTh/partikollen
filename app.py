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
from google import genai
from google.cloud import firestore
from google.oauth2 import service_account

# Fixar teckenkodning och stora heltal
sys.stdout.reconfigure(encoding='utf-8')
sys.set_int_max_str_digits(0)

# --- 1. KONFIGURATION & DATABAS-KOPPLING ---
st.set_page_config(page_title="Partikollen Dashboard", page_icon="🏛️", layout="wide")

# HÄMTA API-NYCKEL (GEMINI)
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    st.error("Ingen Google API-nyckel hittades i Secrets.")
    st.stop()

client = genai.Client(api_key=API_KEY)

# KOPPLA TILL FIRESTORE (DATABASEN)
if "FIREBASE_KEY" in st.secrets:
    try:
        key_dict = json.loads(st.secrets["FIREBASE_KEY"])
        creds = service_account.Credentials.from_service_account_info(key_dict)
        db = firestore.Client(credentials=creds, project=key_dict["project_id"])
        st.sidebar.success("✅ Molndatabas")
    except Exception as e:
        st.error(f"Kunde inte koppla till databasen: {e}")
        st.stop()
else:
    st.warning("⚠️ Ingen databasnyckel hittad.")
    st.stop()

# --- 2. HJÄLPFUNKTIONER ---

def stada_html(html_text):
    if not html_text: return ""
    html_text = html_text.replace("</td>", " ").replace("</th>", " ").replace("</tr>", "\n") 
    text = re.sub(r'<[^<]+?>', ' ', html_text)
    return " ".join(text.split())

def hitta_parti(dok, doktyp):
    if doktyp == 'bet': return "Utskottet"
    if doktyp == 'prop': return "Regeringen"
    if dok.get('parti') and dok.get('parti') != "-": return dok['parti'].upper()
    text = (dok.get('subtitel') or "") + " " + (dok.get('titel') or "")
    match = re.search(r'\(([A-Z]{1,2})\)', text)
    if match: return match.group(1)
    return "-"

def hamta_full_text(doc_dict):
    """Om dokumentet är uppdelat, hämta resten och limma ihop."""
    texten = doc_dict.get('full_text', '')
    
    if doc_dict.get('is_chunked'):
        try:
            # Hämta delarna från under-kollektionen
            parts_ref = db.collection("riksdagen_docs").document(doc_dict['dok_id']).collection('text_parts')
            parts = parts_ref.stream()
            
            # Sortera dem så de kommer i rätt ordning (1, 2, 3...)
            sorted_parts = sorted([p.to_dict() for p in parts], key=lambda x: x['index'])
            
            for part in sorted_parts:
                texten += part.get('text_part', '')
        except Exception as e:
            st.warning(f"Kunde inte hämta alla textdelar: {e}")
            
    return texten

@st.cache_data(ttl=600)
def ladda_data_fran_db():
    docs_list = []
    try:
        docs = db.collection("riksdagen_docs").stream()
        for doc in docs:
            docs_list.append(doc.to_dict())
    except Exception as e:
        st.error(f"Kunde inte läsa från databasen: {e}")
        return pd.DataFrame()
    
    if not docs_list: return pd.DataFrame()

    df = pd.DataFrame(docs_list)
    if "datum" in df.columns:
        df["datum"] = pd.to_datetime(df["datum"], errors='coerce')
    return df

def spara_till_db(post):
    # Enkel spar-funktion för nya dokument (vi antar att de är små nog för nu)
    doc_ref = db.collection("riksdagen_docs").document(post['dok_id'])
    doc_ref.set(post)

# --- 3. UI ---
with st.sidebar:
    st.header("⚙️ Filter")
    idag = datetime.date.today()
    en_manad_sen = idag - datetime.timedelta(days=30)
    start_datum = st.date_input("Från:", en_manad_sen)
    slut_datum = st.date_input("Till:", idag)

st.title("🏛️ Partikollen Cloud ☁️")

tab1, tab2, tab3 = st.tabs(["📡 Inhämtning", "🔍 Utforskaren", "🧠 AI-Analys"])

# === FLIK 1: INHÄMTNING ===
with tab1:
    st.header("Uppdatera Molndatabasen")
    c1, c2 = st.columns(2)
    with c1:
        check_tal = st.checkbox("Debatter", value=True)
        check_mot = st.checkbox("Motioner & Prop", value=True)
        check_beslut = st.checkbox("Beslut", value=True)
        max_sidor = st.number_input("Max sidor:", min_value=1, value=5)
        btn_start = st.button("🚀 Hämta nytt från Riksdagen", type="primary")

    if btn_start:
        status = st.status("Startar moln-inhämtning...", expanded=True)
        from_str = start_datum.strftime("%Y-%m-%d")
        tom_str = slut_datum.strftime("%Y-%m-%d")

        def kor_inhamtning(doktyp, label):
            status.write(f"Söker efter: {label}...")
            page = 1
            totalt = 0
            while page <= max_sidor:
                url = f"https://data.riksdagen.se/dokumentlista/?doktyp={doktyp}&sz=20&p={page}&from={from_str}&tom={tom_str}&utformat=json"
                try:
                    resp = requests.get(url)
                    data = resp.json()
                    if 'dokumentlista' not in data: break
                    docs = data['dokumentlista'].get('dokument', [])
                    if not docs: break
                    if isinstance(docs, dict): docs = [docs]

                    nya = 0
                    for dok in docs:
                        did = dok['dok_id']
                        # Här skulle man kunna kolla om ID finns, men set() är billigt
                        h_url = f"https://data.riksdagen.se/dokument/{did}.html"
                        h_resp = requests.get(h_url)
                        if h_resp.status_code == 200:
                            ren_text = stada_html(h_resp.text)
                            if doktyp == "mot": k = "Motion"
                            elif doktyp == "prop": k = "Proposition"
                            elif doktyp == "bet": k = "Beslut"
                            else: k = "Debatt"
                            
                            post = {
                                'dok_id': did, 'titel': dok['titel'], 'datum': dok['datum'],
                                'full_text': ren_text, 'typ': doktyp, 'Kategori': k,
                                'parti': hitta_parti(dok, doktyp), 'subtitel': dok.get('subtitel', ''),
                                'beslut': dok.get('beslut', '')
                            }
                            spara_till_db(post)
                            nya += 1
                            time.sleep(0.05)
                    totalt += nya
                    status.write(f"{label} Sida {page}: {nya} st.")
                    if nya == 0: break
                    page += 1
                except Exception as e:
                    status.warning(f"Fel: {e}")
                    page += 1
            return totalt

        tot = 0
        if check_tal: tot += kor_inhamtning("prot", "Debatter")
        if check_mot: tot += kor_inhamtning("mot", "Motioner") + kor_inhamtning("prop", "Propositioner")
        if check_beslut: tot += kor_inhamtning("bet", "Beslut")
        
        status.success(f"Klar! Hämtade {tot} dokument.")
        st.cache_data.clear()
        time.sleep(2)
        st.rerun()

# === FLIK 2: UTFORSKAREN ===
with tab2:
    st.header("🔍 Utforska")
    if "valt_dokument" not in st.session_state: st.session_state["valt_dokument"] = None

    with st.spinner("Hämtar index..."):
        df = ladda_data_fran_db()
    
    if df.empty:
        st.warning("Databasen är tom.")
    else:
        # --- LÄS-VY ---
        if st.session_state["valt_dokument"] is not None:
            doc_meta = st.session_state["valt_dokument"]
            if st.button("⬅️ Tillbaka"):
                st.session_state["valt_dokument"] = None
                st.rerun()
            
            st.divider()
            st.subheader(f"{doc_meta['titel']}")
            st.caption(f"{doc_meta['datum']} | {doc_meta['parti']} | ID: {doc_meta['dok_id']}")
            
            # HÄMTA HELA TEXTEN (INKL CHUNKS)
            with st.spinner("Hämtar hela texten..."):
                komplett_text = hamta_full_text(doc_meta)
            
            st.markdown(komplett_text)
        
        # --- LIST-VY ---
        else:
            c1, c2, c3, c4 = st.columns(4)
            with c1: valda_partier = st.multiselect("Parti:", sorted([x for x in df["parti"].astype(str).unique() if x != 'nan']))
            with c2: valda_typer = st.multiselect("Typ:", sorted([x for x in df["Kategori"].astype(str).unique() if x != 'nan']))
            with c3: visnings_datum = st.date_input("Period:", (df["datum"].min().date(), df["datum"].max().date()))
            with c4: sok = st.text_input("Sök:")

            v_df = df.copy()
            if len(visnings_datum) == 2:
                v_df = v_df[(v_df['datum'].dt.date >= visnings_datum[0]) & (v_df['datum'].dt.date <= visnings_datum[1])]
            if valda_partier: v_df = v_df[v_df["parti"].isin(valda_partier)]
            if valda_typer: v_df = v_df[v_df["Kategori"].isin(valda_typer)]
            if sok:
                v_df = v_df[v_df["full_text"].str.contains(sok, case=False, na=False) | v_df["titel"].str.contains(sok, case=False, na=False)]
            
            v_df = v_df.sort_values("datum", ascending=False)
            st.session_state["ai_urval"] = v_df 
            
            per_sida = 15
            antal_sidor = math.ceil(len(v_df) / per_sida)
            col_info, col_nav = st.columns([3, 2])
            with col_info: st.caption(f"Visar {len(v_df)} dokument.")
            with col_nav: sida = st.number_input("Sida", 1, max(1, antal_sidor), 1) if antal_sidor > 1 else 1

            start = (sida - 1) * per_sida
            for _, r in v_df.iloc[start : start + per_sida].iterrows():
                with st.container():
                    c1, c2, c3, c4 = st.columns([1.5, 1, 4, 1.5])
                    c1.write(r['datum'].date())
                    c2.write(r['parti'])
                    c3.write(r['titel'])
                    if c4.button("📖 Läs", key=r['dok_id']):
                        st.session_state["valt_dokument"] = r.to_dict()
                        st.rerun()
                    st.divider()

# === FLIK 3: AI ===
with tab3:
    st.header("🧠 Analys")
    if "ai_urval" in st.session_state and not st.session_state["ai_urval"].empty:
        urval = st.session_state["ai_urval"].head(10) # Färre dokument för snabbhet
        q = st.text_area("Fråga:", "Vad är de viktigaste punkterna?")
        if st.button("Analysera"):
            with st.spinner("AI läser..."):
                ctx = ""
                for _, r in urval.iterrows():
                    # Vi tar bara första biten text för AI-analys för att spara tokens
                    raw_text = r['full_text'][:2000] 
                    ctx += f"\n--- {r['titel']} ---\n{raw_text}...\n"
                try:
                    res = client.models.generate_content(model="gemini-1.5-flash", contents=f"Fråga: {q}\nUnderlag:\n{ctx}")
                    st.markdown(res.text)
                except Exception as e: st.error(e)