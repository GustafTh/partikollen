import json
from google import genai
import os
import sys

# Fixar teckenkodning
sys.stdout.reconfigure(encoding='utf-8')

print("--- PARTIKOLLEN: SJÄLVLÄKANDE VERSION ---")

# DIN NYCKEL
MIN_API_NYCKEL = "AIzaSyA3XFB_3cCwzQdWhzv2m4Z0Pw62K8y-qWg"
client = genai.Client(api_key=MIN_API_NYCKEL)

# --- STEG 1: HITTA RÄTT MODELL AUTOMATISKT ---
print("⚙️  Kontaktar Google för att hitta rätt modellnamn...")

vald_modell = None
try:
    # Vi hämtar listan på vad ditt konto får använda
    alla_modeller = client.models.list()
    
    # Vi letar efter en bra modell (Flash är snabbast, Pro är smartast)
    kandidater = []
    for m in alla_modeller:
        namn = m.name.lower()
        if "gemini" in namn and "vision" not in namn:
            kandidater.append(m.name)
    
    # Prioriteringsordning: Först Flash, sen Pro, sen vad som helst
    for k in kandidater:
        if "flash" in k and "1.5" in k:
            vald_modell = k
            break
    
    # Om vi inte hittade Flash, ta första bästa Gemini
    if not vald_modell and kandidater:
        vald_modell = kandidater[0]

    if vald_modell:
        print(f"✅ Hittade och valde modellen: {vald_modell}")
        # Ofta heter de 'models/gemini...', vi strippar 'models/' för säkerhets skull om SDK vill det
        if "/" in vald_modell:
            print(f"   (Systemnamn: {vald_modell})")
    else:
        print("❌ Kunde inte hitta någon 'Gemini'-modell kopplad till din nyckel.")
        print("   Se till att du aktiverat 'Google AI Studio' eller billing korrekt.")
        exit()

except Exception as e:
    print(f"❌ Kunde inte lista modeller: {e}")
    # Nödlösning: Vi testar ett hårdkodat namn som ofta funkar för betalande
    vald_modell = "gemini-1.5-flash-001"
    print(f"⚠️  Försöker tvinga användning av: {vald_modell}")

# --- STEG 2: LADDA DATAN ---
filer = ["riksdagen_host24_framat.json", "riksdagen_motioner.json"]
filnamn = ""
for f in filer:
    if os.path.exists(f):
        filnamn = f
        break

if not filnamn:
    print("❌ Ingen datafil hittades. Kör hämtaren först.")
    exit()

with open(filnamn, "r", encoding="utf-8") as f:
    data = json.load(f)
print(f"✅ Data laddad: {len(data)} dokument.")

# --- STEG 3: ANALYS-LOOPEN ---
while True:
    print("\n" + "-"*40)
    amne = input("Vilket ämne vill du analysera? (eller 'avsluta'): ").lower()
    
    if amne in ["avsluta", "exit", "slut", "q"]:
        break

    print(f"🔍 Letar efter '{amne}'...")
    
    texter = []
    for rad in data:
        innehall = rad.get('full_text', '') or rad.get('titel', '')
        if amne in innehall.lower():
            talare = rad.get('talare', 'Okänd')
            parti = rad.get('parti', '?')
            datum = rad.get('dok_datum', rad.get('datum', '?'))
            
            # Max 1000 tecken per text
            utdrag = innehall[:1000].replace("\n", " ")
            texter.append(f"--- {talare} ({parti}), {datum} ---\n{utdrag}")
            
            if len(texter) >= 20: # Tak på 20 texter
                break
    
    if not texter:
        print("❌ Hittade inga träffar i din databas.")
        continue

    print(f"🧠 Skickar {len(texter)} dokument till AI...")

    prompt = f"""
    Du är en skarp politisk analytiker.
    Ämne: "{amne.upper()}".
    
    Analysera bifogade texter från Riksdagen och svara på svenska:

    1. ⚔️ KONFLIKTEN
       Vad bråkar de om? Vad är kärnan?

    2. 📢 STÅNDPUNKTER
       Vad tycker de inblandade partierna?

    3. 💬 CITAT
       Ett kort, talande citat från texterna.

    4. 🔮 SLUTSATS
       Vem verkar ha övertaget i debatten?

    UNDERLAG:
    {"\n".join(texter)}
    """

    try:
        # Här använder vi namnet vi hittade automatiskt
        response = client.models.generate_content(
            model=vald_modell,
            contents=prompt
        )
        
        print("\n" + "="*60)
        print(f"ANALYS AV: {amne.upper()}") 
        print("-" * 30)
        print(response.text)
        print("="*60)

    except Exception as e:
        print(f"❌ Något gick snett vid genereringen: {e}")