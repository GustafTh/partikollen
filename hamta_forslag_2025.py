import requests
import json
import time
import re
import os
import sys

# Fixar teckenkodning
sys.stdout.reconfigure(encoding='utf-8')

print("--- FÖRSLAGS-HÄMTAREN (MOTIONER & PROPOSITIONER) ---")
print("Hämtar både oppositionens förslag och regeringens lagförslag.")
print("Tvättar texten ren från kod och skräp.")

filnamn = "riksdagen_forslag.json"
riksmoten = ["2024%2F25"] 

# Vi hämtar både Motioner (mot) och Propositioner (prop)
doktyper = ["mot", "prop"]

data_lista = []
unika_id = set()

# Ladda gammal data
if os.path.exists(filnamn):
    with open(filnamn, "r", encoding="utf-8") as f:
        data_lista = json.load(f)
        unika_id = set(rad['dok_id'] for rad in data_lista)

print(f"Startar med {len(data_lista)} förslag i databasen.")

# --- VÅR SMARTA TVÄTTMASKIN ---
def stada_html(html_text):
    if not html_text:
        return ""
    # Ta bort head, style, script och kommentarer
    text = re.sub(r'<head.*?>.*?</head>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'', '', text, flags=re.DOTALL)
    # Ta bort taggar
    text = re.sub(r'<[^<]+?>', ' ', text)
    # Snygga till
    text = " ".join(text.split())
    return text

# --- HUVUDLOOPEN ---
for rm in riksmoten:
    for typ in doktyper:
        page = 1
        more_pages = True
        
        typ_namn = "Motioner" if typ == "mot" else "Propositioner"
        print(f"\n>>> Hämtar {typ_namn} ({typ}) för {rm.replace('%2F', '/')} <<<")
        
        while more_pages:
            # Vi hämtar 50 åt gången för att det ska gå undan
            url = f"https://data.riksdagen.se/dokumentlista/?rm={rm}&doktyp={typ}&sz=50&p={page}&utformat=json"
            
            try:
                svar = requests.get(url)
                data = svar.json()
                
                # Säkerhetskoll om listan är tom
                if 'dokumentlista' not in data:
                    print(f"Slut på {typ_namn}.")
                    break
                
                dokumenten = data['dokumentlista'].get('dokument')
                
                if not dokumenten:
                    print(f"Slut på {typ_namn} vid sida {page}.")
                    break
                    
                if isinstance(dokumenten, dict):
                    dokumenten = [dokumenten]

                print(f"Sida {page:<3} (Datum: {dokumenten[0].get('datum', 'Okänt')})... ", end="")
                
                nya_sparade = 0
                
                for dok in dokumenten:
                    did = dok['dok_id']
                    
                    if did not in unika_id:
                        # Hämta HTML-texten
                        url_html = f"https://data.riksdagen.se/dokument/{did}.html"

                        try:
                            html_svar = requests.get(url_html)
                            if html_svar.status_code == 200:
                                raw = html_svar.text
                                
                                # TVÄTTA TEXTEN
                                ren_text = stada_html(raw)
                                
                                # Vi sparar lite extra info här som är bra för motioner
                                sparad_dok = {
                                    'dok_id': did,
                                    'titel': dok['titel'],
                                    'datum': dok['datum'],
                                    'typ': 'motion' if typ == 'mot' else 'proposition',
                                    'subtyp': dok.get('subtyp', ''), # T.ex. "partimotion"
                                    'parti': dok.get('parti', ''),   # Vilket parti la förslaget?
                                    'full_text': ren_text
                                }
                                
                                data_lista.append(sparad_dok)
                                unika_id.add(did)
                                nya_sparade += 1
                            
                            time.sleep(0.05) # Liten paus
                        except:
                            pass

                print(f"Sparade {nya_sparade} st. (Totalt: {len(data_lista)})")
                
                # Spara ofta
                with open(filnamn, "w", encoding="utf-8") as f:
                    json.dump(data_lista, f, indent=4, ensure_ascii=False)
                    
                page += 1
                
            except Exception as e:
                print(f"Ett fel uppstod: {e}. Försöker nästa sida...")
                # Om en sida kraschar, hoppa framåt istället för att dö
                page += 1
                time.sleep(2)

print(f"\n✅ KLART! {len(data_lista)} förslag sparade i '{filnamn}'.")