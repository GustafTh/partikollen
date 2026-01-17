import requests
import json
import time
import re
import os

print("--- STABIL MASS-HÄMTARE ---")
print("Hämtar så långt bak det går utan att fastna i loopar.")
print("Avbryt med Ctrl+C när du är nöjd.\n")

filnamn = "riksdagen_stor_data.json"
total_lista = []
unika_id = set()

# 1. Ladda befintlig data
if os.path.exists(filnamn):
    try:
        with open(filnamn, "r", encoding="utf-8") as f:
            total_lista = json.load(f)
            unika_id = set(rad['anforande_id'] for rad in total_lista)
        print(f"Laddade in {len(total_lista)} gamla tal från filen.")
    except:
        print("Kunde inte läsa filen, startar ny lista.")

# Variabler för att upptäcka loopar
last_first_id = ""
consecutive_empty_pages = 0

page = 1
while True:
    # Vi hämtar nyast först
    url = f"https://data.riksdagen.se/anforandelista/?sz=50&p={page}&utformat=json&sort=datum&sortorder=desc"
    
    try:
        svar = requests.get(url)
        data = svar.json()
        
        # Är listan slut?
        if 'anforandelista' not in data or not data['anforandelista']['anforande']:
            print("Listan tog slut hos Riksdagen.")
            break
            
        anforanden = data['anforandelista']['anforande']
        
        # --- LOOP-SKYDDET ---
        # Vi kollar ID på det första talet på sidan.
        # Är det exakt samma som förra gången? Då har servern hängt sig.
        nuvarande_first_id = anforanden[0]['anforande_id']
        if nuvarande_first_id == last_first_id:
            print("\n⚠️  UPPTÄCKTE EN LOOP! Servern skickar samma sida igen.")
            print("Avslutar hämtningen snyggt.")
            break
        last_first_id = nuvarande_first_id
        # --------------------

        aktuellt_datum = anforanden[0]['dok_datum']
        print(f"Sida {page} (Datum: {aktuellt_datum})... ", end="")

        nya_pa_sidan = 0
        
        for rad in anforanden:
            datum = rad['dok_datum']
            aid = rad['anforande_id']
            
            # Vi sparar allt vi kommer över som vi inte har
            # (Vi filtrerar inte hårt på åratal här för att inte missa något i skarvarna)
            if aid not in unika_id:
                
                # Hämta HTML
                url_html = rad['anforande_url_xml'].replace(".xml", ".html")
                try:
                    html_svar = requests.get(url_html)
                    if html_svar.status_code == 200:
                        raw = html_svar.text
                        ren_text = re.sub('<[^<]+?>', '', raw)
                        ren_text = " ".join(ren_text.split())
                        
                        if len(ren_text) > 100:
                            rad['full_text'] = ren_text
                            total_lista.append(rad)
                            unika_id.add(aid)
                            nya_pa_sidan += 1
                    time.sleep(0.05) 
                except:
                    pass

        print(f"Hittade {nya_pa_sidan} nya tal.")

        # Om vi hittar 0 nya tal på 3 sidor i rad, då är vi nog klara
        if nya_pa_sidan == 0:
            consecutive_empty_pages += 1
        else:
            consecutive_empty_pages = 0
            
        if consecutive_empty_pages >= 3:
            print("\nInga nya tal hittade på 3 sidor. Vi verkar vara ikapp!")
            break

        # Spara
        with open(filnamn, "w", encoding="utf-8") as f:
            json.dump(total_lista, f, indent=4, ensure_ascii=False)
            
        page += 1
        
    except Exception as e:
        print(f"Fel: {e}. Väntar lite...")
        time.sleep(5)

print(f"\n✅ KLART! Du har nu en databas med {len(total_lista)} tal.")