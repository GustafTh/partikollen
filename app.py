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

# Fixar teckenkodning för Windows-terminaler
sys.stdout.reconfigure(encoding='utf-8')

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Partikollen Dashboard", page_icon="🏛️", layout="wide")

# HÄMTA API-NYCKEL SÄKERT
# Kollar secrets (molnet) eller input (lokalt)
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    # Hårdkodad fallback för din lokala testning (Ta bort innan GitHub publicering om du vill vara extra säker)
    API_KEY = "AIzaSyA3XFB_3cCwzQdWhzv2m4Z0Pw62K8y-qWg"

if API_KEY:
    client = genai.Client(api_key=API_KEY)

# FILNAMN
FIL_PROTOKOLL = "riksdagen_protokoll.json"
FIL_FORSLAG = "riksdagen_forslag.json"
FIL_BESLUT = "riksdagen_beslut.json"

# --- 2. HJÄLPFUNKTIONER ---

def stada_html(html_text):
    """Tvättar texten ren från kod."""
    if not html_text: return ""
    
    # Hantera tabeller snyggt (viktigt för beslut/voteringar)
    html_text = html_text.replace("</td>", " ").replace("</th>", " ")
    html_text = html_text.replace("</tr>", "\n") 
    
    text = re.sub(r'<head.*?>.*?</head>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^<]+?>', ' ', text)
    
    return " ".join(text.split())

def ladda_data():
    """Laddar in alla filer till en gemensam lista."""
    all_data = []
    
    # 1. Protokoll (Debatter)
    if os.path.exists(FIL_PROTOKOLL):
        with open(FIL_PROTOKOLL, "r", encoding="utf-8") as f:
            data = json.load(f)
            for rad in data:
                rad["Kategori"] = "Debatt"
                if "parti" not in rad: rad["parti"] = "-"
                all_data.append(rad)
    
    # 2. Förslag (Motioner/Prop)
    if os.path.exists(FIL_FORSLAG):
        with open(FIL_FORSLAG, "r", encoding="utf-8") as f:
            data = json.load(f)
            for rad in data:
                typ = rad.get("typ", "Förslag")
                if typ == "mot": rad["Kategori"] = "Motion"
                elif typ == "prop": rad["Kategori"] = "Proposition"
                else: rad["Kategori"] = "Förslag"
                all_data.append(rad)

    # 3. Beslut (Betänkanden)
    if os.path.exists(FIL_BESLUT):
        with open(FIL_BESLUT, "r", encoding="utf-8") as f:
            data = json.load(f)
            for rad in data:
                rad["Kategori"] = "Beslut"
                rad["parti"] = "Utskottet" # Betänkanden kommer från utskott
                all_data.append(rad)
    
    if not all_data: return pd.DataFrame()
    
    df = pd.DataFrame(all_data)
    # Gör om datumsträngar till riktiga datum
    if "datum" in df.columns:
        df["datum"] = pd.to_datetime(df["datum"], errors='coerce')
    return df

# --- 3. UI & SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Inställningar")
    
    st.subheader("Sökintervall (Inhämtning)")
    idag = datetime.date.today()
    # Default 30 dagar bakåt
    en_manad_sen = idag - datetime.timedelta(days=30)
    
    start_datum = st.date_input("Från:", en_manad_sen)
    slut_datum = st.date_input("Till:", idag)
    
    st.divider()
    st.caption("Databasstatus:")
    if os.path.exists(FIL_PROTOKOLL): st.success(f"Debatter: Finns")
    else: st.error("Debatter: Saknas")
    if os.path.exists(FIL_FORSLAG): st.success(f"Förslag: Finns")
    else: st.error("Förslag: Saknas")
    if os.path.exists(FIL_BESLUT): st.success(f"Beslut: Finns")
    else: st.error("Beslut: Saknas")

# --- 4. HUVUDPROGRAM ---
st.title("🏛️ Partikollen Dashboard")

if not API_KEY:
    st.warning("⚠️ Ingen API-nyckel hittades. Appen fungerar inte fullt ut.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📡 Inhämtning", "🔍 Utforskaren", "🧠 AI-Analys"])

# === FLIK 1: INHÄMTNING ===
with tab1:
    st.header("Uppdatera Databasen")
    st.markdown("Hämtar dokument baserat på dina datum i menyn till vänster.")
    
    col1, col2 = st.columns(2)
    with col1:
        check_tal = st.checkbox("Debatter (Protokoll)", value=True)
        check_mot = st.checkbox("Motioner & Propositioner", value=True)
        check_beslut = st.checkbox("Beslut (Betänkanden)", value=True)
        
        max_sidor = st.number_input("Max sidor att söka:", min_value=1, value=10)
        btn_start = st.button("🚀 Starta Uppdatering", type="primary")

    if btn_start:
        status = st.status("Startar robotarna...", expanded=True)
        
        # Formatera datum för API
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
                # HÄR ÄR FIXEN: Vi har tagit bort "&rm=..." så den går BARA på datum.
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
                            # Hämta HTML
                            h_url = f"https://data.riksdagen.se/dokument/{did}.html"
                            h_resp = requests.get(h_url)
                            
                            if h_resp.status_code == 200:
                                ren_text = stada_html(h_resp.text)
                                
                                post = {
                                    'dok_id': did,
                                    'titel': dok['titel'],
                                    'datum': dok['datum'],
                                    'full_text': ren_text,
                                    'typ': doktyp,
                                    'parti': dok.get('parti', '-'),
                                    'beslut': dok.get('beslut', '')
                                }
                                befintlig.append(post)
                                nya_poster.append(post)
                                unika_id.add(did)
                                nya_pa_sidan += 1
                                time.sleep(0.05)
                    
                    status.write(f"{label} Sida {page}: Hittade {nya_pa_sidan} nya.")
                    
                    # Stop-loss: Om sidan är tom på nya grejer, sluta leta
                    if nya_pa_sidan == 0:
                        status.info(f"✅ Ikapp med {label}.")
                        break
                    page += 1
                    
                except Exception as e:
                    # Ignorera fel och försök nästa sida
                    page += 1
            
            if nya_poster:
                with open(filnamn, "w", encoding="utf-8") as f:
                    json.dump(befintlig, f, indent=4, ensure_ascii=False)
                status.success(f"Sparade {len(nya_poster)} nya {label}.")
            else:
                status.write(f"Inga nya {label}.")

        # Kör jobben
        if check_tal: hämta_kategori(FIL_PROTOKOLL, "prot", "Debatter")
        if check_mot: 
            hämta_kategori(FIL_FORSLAG, "mot", "Motioner")
            hämta_kategori(FIL_FORSLAG, "prop", "Propositioner")
        if check_beslut: hämta_kategori(FIL_BESLUT, "bet", "Beslut")

        status.update(label="Klar!", state="complete")
        time.sleep(1)
        st.rerun()

# === FLIK 2: UTFORSKAREN ===
with tab2:
    st.header("🔍 Utforska & Filtrera")
    df = ladda_data()
    
    if df.empty:
        st.warning("Databasen är tom. Gå till fliken 'Inhämtning' först.")
    else:
        st.caption(f"Totalt: {len(df)} dokument.")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            partier = sorted(df["parti"].astype(str).unique())
            valda_partier = st.multiselect("Parti:", partier)
        with c2:
            typer = sorted(df["Kategori"].unique())
            valda_typer = st.multiselect("Typ:", typer)
        with c3:
            # Datumfilter för VISNING (påverkar bara tabellen, inte inhämtning)
            if not df.empty:
                d_min = df["datum"].min().date()
                d_max = df["datum"].max().date()
                visnings_datum = st.date_input("Visa period:", (d_min, d_max))
        with c4:
            sok = st.text_input("Söktext:")

        # Applicera filter
        v_df = df.copy()
        
        if not df.empty and 'visnings_datum' in locals() and len(visnings_datum) == 2:
            v_df = v_df[(v_df['datum'].dt.date >= visnings_datum[0]) & (v_df['datum'].dt.date <= visnings_datum[1])]
            
        if valda_partier: v_df = v_df[v_df["parti"].isin(valda_partier)]
        if valda_typer: v_df = v_df[v_df["Kategori"].isin(valda_typer)]
        if sok:
            v_df = v_df[v_df["full_text"].str.contains(sok, case=False, na=False) | v_df["titel"].str.contains(sok, case=False, na=False)]

        st.info(f"Visar {len(v_df)} dokument.")
        st.dataframe(v_df[["datum", "Kategori", "parti", "titel"]].sort_values("datum", ascending=False), use_container_width=True, hide_index=True)
        
        st.session_state["ai_urval"] = v_df

# === FLIK 3: AI-ANALYS ===
with tab3:
    st.header("🧠 Analys")
    
    if "ai_urval" in st.session_state and not st.session_state["ai_urval"].empty:
        urval = st.session_state["ai_urval"]
        st.write(f"Analyseras: **{len(urval)}** st.")
        
        if len(urval) > 25:
            st.caption("Tar de 25 senaste för att spara tid.")
            urval = urval.head(25)

        q_default = "Sammanfatta konflikterna och ståndpunkterna."
        if "Beslut" in urval["Kategori"].values:
            q_default = "Vad handlar dessa beslut om? Vilka reservationer finns? Vad blev resultatet?"

        fraga = st.text_area("Fråga:", q_default)
        
        if st.button("Kör Analys"):
            with st.spinner("Tänker..."):
                ctx = ""
                for _, r in urval.iterrows():
                    ctx += f"\n--- {r['Kategori'].upper()} ({r['datum']}) ---\nTITEL: {r['titel']}\nTEXT: {str(r['full_text'])[:1500]}...\n"
                
                prompt = f"Du är politisk expert. Svara på frågan baserat på detta:\nFRÅGA: {fraga}\nUNDERLAG:\n{ctx}"
                
                try:
                    resp = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
                    st.markdown(resp.text)
                except Exception as e:
                    st.error(str(e))
    else:
        st.warning("Välj data i Utforskaren först.")