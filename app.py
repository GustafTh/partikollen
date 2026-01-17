import streamlit as st
import pandas as pd
import json
import os
import re
import requests
import time
import datetime
from google import genai
import sys

# Fixar teckenkodning
sys.stdout.reconfigure(encoding='utf-8')

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Partikollen Dashboard", page_icon="🏛️", layout="wide")

# HÄMTA API-NYCKEL
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = "AIzaSyA3XFB_3cCwzQdWhzv2m4Z0Pw62K8y-qWg" # Din nyckel

if API_KEY:
    client = genai.Client(api_key=API_KEY)

# FILNAMN
FIL_PROTOKOLL = "riksdagen_protokoll.json"
FIL_FORSLAG = "riksdagen_forslag.json"
FIL_BESLUT = "riksdagen_beslut.json"

# --- 2. HJÄLPFUNKTIONER ---

def stada_html(html_text):
    if not html_text: return ""
    html_text = html_text.replace("</td>", " ").replace("</th>", " ").replace("</tr>", "\n") 
    text = re.sub(r'<head.*?>.*?</head>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^<]+?>', ' ', text)
    return " ".join(text.split())

def hitta_parti(dok):
    """Försöker lista ut partiet om fältet är tomt."""
    
    # 1. Om API:et faktiskt ger oss ett parti, använd det
    if dok.get('parti') and dok.get('parti') != "-":
        return dok['parti'].upper()
    
    # 2. Om det är en proposition kommer den från Regeringen
    if dok.get('doktyp') == 'prop':
        return "Regeringen"
        
    # 3. Leta i undertiteln efter parenteser, t.ex. "av Namn Namn (S)"
    text_att_soka = (dok.get('subtitel') or "") + " " + (dok.get('titel') or "")
    
    # Regex för att hitta (S), (M), (SD) osv.
    match = re.search(r'\(([A-Z]{1,2})\)', text_att_soka)
    if match:
        return match.group(1)
        
    return "-"

def ladda_data():
    all_data = []
    
    # 1. Protokoll
    if os.path.exists(FIL_PROTOKOLL):
        with open(FIL_PROTOKOLL, "r", encoding="utf-8") as f:
            data = json.load(f)
            for rad in data:
                rad["Kategori"] = "Debatt"
                if "parti" not in rad: rad["parti"] = "-"
                all_data.append(rad)
    
    # 2. Förslag
    if os.path.exists(FIL_FORSLAG):
        with open(FIL_FORSLAG, "r", encoding="utf-8") as f:
            data = json.load(f)
            for rad in data:
                typ = rad.get("typ", "Förslag")
                if typ == "mot": rad["Kategori"] = "Motion"
                elif typ == "prop": rad["Kategori"] = "Proposition"
                else: rad["Kategori"] = "Förslag"
                all_data.append(rad)

    # 3. Beslut
    if os.path.exists(FIL_BESLUT):
        with open(FIL_BESLUT, "r", encoding="utf-8") as f:
            data = json.load(f)
            for rad in data:
                rad["Kategori"] = "Beslut"
                # Beslut (betänkanden) kommer från Utskott
                rad["parti"] = "Utskottet"
                all_data.append(rad)
    
    if not all_data: return pd.DataFrame()
    
    df = pd.DataFrame(all_data)
    if "datum" in df.columns:
        df["datum"] = pd.to_datetime(df["datum"], errors='coerce')
    return df

# --- 3. UI ---
with st.sidebar:
    st.header("⚙️ Inställningar")
    idag = datetime.date.today()
    en_manad_sen = idag - datetime.timedelta(days=30)
    start_datum = st.date_input("Från:", en_manad_sen)
    slut_datum = st.date_input("Till:", idag)
    
    st.divider()
    # Visa status med färger
    if os.path.exists(FIL_PROTOKOLL): st.success("Debatter: Finns")
    else: st.error("Debatter: Saknas")
    
    if os.path.exists(FIL_FORSLAG): st.success("Förslag: Finns")
    else: st.error("Förslag: Saknas")
    
    if os.path.exists(FIL_BESLUT): st.success("Beslut: Finns")
    else: st.error("Beslut: Saknas (Kör inhämtning!)")

st.title("🏛️ Partikollen Dashboard")

if not API_KEY:
    st.warning("⚠️ Ingen API-nyckel hittades.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📡 Inhämtning", "🔍 Utforskaren", "🧠 AI-Analys"])

# === FLIK 1: INHÄMTNING ===
with tab1:
    st.header("Uppdatera Databasen")
    st.info("Om 'Beslut' saknas i sidomenyn -> Kryssa i Beslut nedan och kör start!")
    
    col1, col2 = st.columns(2)
    with col1:
        check_tal = st.checkbox("Debatter (Protokoll)", value=True)
        check_mot = st.checkbox("Motioner & Propositioner", value=True)
        check_beslut = st.checkbox("Beslut (Betänkanden)", value=True)
        max_sidor = st.number_input("Max sidor:", min_value=1, value=10)
        btn_start = st.button("🚀 Starta Uppdatering", type="primary")

    if btn_start:
        status = st.status("Startar...", expanded=True)
        from_str = start_datum.strftime("%Y-%m-%d")
        tom_str = slut_datum.strftime("%Y-%m-%d")

        def hämta_kategori(filnamn, doktyp, label):
            status.write(f"📂 Bearbetar: {label}...")
            befintlig = []
            if os.path.exists(filnamn):
                with open(filnamn, "r", encoding="utf-8") as f:
                    befintlig = json.load(f)
            
            unika_id = set(d['dok_id'] for d in befintlig)
            nya_poster = []
            
            page = 1
            while page <= max_sidor:
                url = f"https://data.riksdagen.se/dokumentlista/?doktyp={doktyp}&sz=20&p={page}&from={from_str}&tom={tom_str}&utformat=json"
                try:
                    resp = requests.get(url)
                    data = resp.json()
                    if 'dokumentlista' not in data: break
                    docs = data['dokumentlista'].get('dokument', [])
                    if not docs: break
                    if isinstance(docs, dict): docs = [docs]

                    nya_pa_sidan = 0
                    for dok in docs:
                        did = dok['dok_id']
                        if did not in unika_id:
                            h_url = f"https://data.riksdagen.se/dokument/{did}.html"
                            h_resp = requests.get(h_url)
                            if h_resp.status_code == 200:
                                ren_text = stada_html(h_resp.text)
                                # ANVÄND PARTI-DETEKTIVEN HÄR
                                parti_fix = hitta_parti(dok)
                                
                                post = {
                                    'dok_id': did,
                                    'titel': dok['titel'],
                                    'datum': dok['datum'],
                                    'full_text': ren_text,
                                    'typ': doktyp,
                                    'parti': parti_fix, 
                                    'subtitel': dok.get('subtitel', ''),
                                    'beslut': dok.get('beslut', '')
                                }
                                befintlig.append(post)
                                nya_poster.append(post)
                                unika_id.add(did)
                                nya_pa_sidan += 1
                                time.sleep(0.05)
                    
                    status.write(f"{label} Sida {page}: {nya_pa_sidan} nya.")
                    if nya_pa_sidan == 0:
                        status.info(f"✅ Ikapp med {label}.")
                        break
                    page += 1
                except Exception as e:
                    page += 1
            
            if nya_poster:
                with open(filnamn, "w", encoding="utf-8") as f:
                    json.dump(befintlig, f, indent=4, ensure_ascii=False)
                status.success(f"Sparade {len(nya_poster)} nya {label}.")
            else:
                status.write(f"Inga nya {label}.")

        if check_tal: hämta_kategori(FIL_PROTOKOLL, "prot", "Debatter")
        if check_mot: hämta_kategori(FIL_FORSLAG, "mot", "Motioner")
        # För propositioner kör vi samma men med 'prop'
        if check_mot: hämta_kategori(FIL_FORSLAG, "prop", "Propositioner")
        if check_beslut: hämta_kategori(FIL_BESLUT, "bet", "Beslut")

        status.update(label="Klar!", state="complete")
        time.sleep(1)
        st.rerun()

# === FLIK 2: UTFORSKAREN ===
with tab2:
    st.header("🔍 Utforska & Läs")
    df = ladda_data()
    
    if df.empty:
        st.warning("Databasen är tom. Gå till fliken 'Inhämtning' först.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            partier = sorted(df["parti"].astype(str).unique())
            valda_partier = st.multiselect("Parti:", partier)
        with c2:
            typer = sorted(df["Kategori"].unique())
            valda_typer = st.multiselect("Typ:", typer)
        with c3:
            if not df.empty:
                d_min = df["datum"].min().date()
                d_max = df["datum"].max().date()
                visnings_datum = st.date_input("Visa period:", (d_min, d_max))
        with c4:
            sok = st.text_input("Söktext:")

        v_df = df.copy()
        if not df.empty and 'visnings_datum' in locals() and len(visnings_datum) == 2:
            v_df = v_df[(v_df['datum'].dt.date >= visnings_datum[0]) & (v_df['datum'].dt.date <= visnings_datum[1])]
        if valda_partier: v_df = v_df[v_df["parti"].isin(valda_partier)]
        if valda_typer: v_df = v_df[v_df["Kategori"].isin(valda_typer)]
        if sok:
            v_df = v_df[v_df["full_text"].str.contains(sok, case=False, na=False) | v_df["titel"].str.contains(sok, case=False, na=False)]

        visnings_tabell = v_df[["datum", "Kategori", "parti", "titel"]].sort_values("datum", ascending=False)
        st.caption(f"Visar {len(v_df)} dokument. Markera en rad för att läsa.")

        # TABELLEN
        event = st.dataframe(
            visnings_tabell,
            use_container_width=True,
            hide_index=True,
            on_select="rerun", # Detta kräver streamlit>=1.36.0
            selection_mode="single-row"
        )

        if event.selection.rows:
            idx = event.selection.rows[0]
            vald_rad = visnings_tabell.iloc[idx]
            full_post = v_df[(v_df['datum'] == vald_rad['datum']) & (v_df['titel'] == vald_rad['titel'])].iloc[0]

            st.markdown("---")
            c_info, c_link = st.columns([3, 1])
            with c_info:
                st.subheader(f"{full_post['titel']}")
                st.markdown(f"**Parti:** {full_post['parti']} | **Typ:** {full_post['Kategori']}")
            with c_link:
                st.link_button("🔗 Öppna på Riksdagen.se", f"http://riksdagen.se/dokument/{full_post['dok_id']}")

            with st.container(border=True):
                st.markdown(full_post['full_text'])
        
        st.session_state["ai_urval"] = v_df

# === FLIK 3: AI ===
with tab3:
    st.header("🧠 Analys")
    if "ai_urval" in st.session_state and not st.session_state["ai_urval"].empty:
        urval = st.session_state["ai_urval"]
        st.write(f"Analyseras: **{len(urval)}** st.")
        if len(urval) > 25:
            st.caption("Tar de 25 senaste.")
            urval = urval.head(25)

        q = st.text_area("Fråga:", "Vad handlar dessa dokument om och vilka konflikter finns?")
        
        if st.button("Kör Analys"):
            with st.spinner("Tänker..."):
                ctx = ""
                for _, r in urval.iterrows():
                    ctx += f"\n--- {r['Kategori']} ({r['parti']}) ---\nTITEL: {r['titel']}\nTEXT: {str(r['full_text'])[:1000]}...\n"
                
                try:
                    resp = client.models.generate_content(model="gemini-1.5-flash", contents=f"Fråga: {q}\nUnderlag:\n{ctx}")
                    st.markdown(resp.text)
                except Exception as e:
                    st.error(str(e))