import requests
import json
import time
import re
import os

print("--- TUNGVIKTAREN: NU LÖSER VI DET ---")
print("Strategi: Vi hämtar 500 tal per sida för att slippa bläddra så mycket.")
print("Vi tvingar också servern att sortera strikt på datum (äldst först).")

filnamn = "riksdagen_host24_framat.json"

# Radera gammalt skräp så vi vet att det funkar
if os.path.exists(filnamn):
    try:
        os.remove(filnamn)
        print("🧹 Raderade gammal fil för att börja om på ny kula.")
    except:
        pass

# 2024/25 och 2025/26
riksmoten = ["2024%2F25", "2025%2F26"]

data_lista = []
unika_id = set()

for rm in riksmoten:
    page = 1
    more_pages = True
    last_first_id = "" 
    
    print(f"\n>>> Startar Riksmöte {rm.replace('%2F', '/')} <<<")
    
    while more_pages:
        # ÄNDRING 1: sz=500 (Hämta massor åt gången)
        # ÄNDRING 2: &sort=datum&sortorder=asc (Tvinga äldst först för att stabilisera listan)
        url = f"https://data.riksdagen.se/anforandelista/?rm={rm}&sz=500&p={page}&utformat=json&sort=datum&sortorder=asc"
        
        try:
            svar = requests.get(url)
            data = svar.json()
            
            if 'anforandelista' not in data or not data['anforandelista']['anforande']:
                print(f"Slut på data för {rm}.")
                break
                
            anforanden = data['anforandelista']['anforande']
            
            # Loop-skydd
            curr_id = anforanden[0]['anforande_id']
            if curr_id == last_first_id:
                print("⚠️ Servern skickade samma sida igen. Vi går vidare.")
                break
            last_first_id = curr_id
            
            datum = anforanden[0]['dok_datum']
            print(f"Sida {page:<2} (Datum: {datum} - ca {len(anforanden)} tal i listan)...")
            
            count_on_page = 0
            
            for i, rad in enumerate(anforanden):
                aid = rad['anforande_id']
                
                if aid not in unika_id:
                    url_html = rad['anforande_url_xml'].replace(".xml", ".html")
                    try:
                        html_svar = requests.get(url_html)
                        if html_svar.status_code == 200:
                            raw = html_svar.text
                            ren_text = re.sub('<[^<]+?>', '', raw)
                            ren_text = " ".join(ren_text.split())
                            
                            if len(ren_text) > 50:
                                rad['full_text'] = ren_text
                                data_lista.append(rad)
                                unika_id.add(aid)
                                count_on_page += 1
                                
                                # Visa att vi lever var 50:e tal
                                if count_on_page % 50 == 0:
                                    print(f"    ...har hämtat {count_on_page} texter på denna sida...")

                        # Liten paus för att inte krascha när vi kör så hårt
                        time.sleep(0.05)
                    except:
                        pass

            print(f" -> Klar med sida {page}. Sparade {count_on_page} nya tal. (Totalt: {len(data_lista)})")
            
            # Spara
            with open(filnamn, "w", encoding="utf-8") as f:
                json.dump(data_lista, f, indent=4, ensure_ascii=False)
                
            page += 1
            
        except Exception as e:
            print(f"Fel: {e}. Försöker igen...")
            time.sleep(5)

print(f"\n✅ KLART! Totalt {len(data_lista)} tal sparade.")