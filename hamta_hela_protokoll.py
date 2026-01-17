import requests
import json
import time
import re
import os
import sys

# Fixar teckenkodning
sys.stdout.reconfigure(encoding='utf-8')

print("--- PROTOKOLL-HÄMTAREN (VERSION 2.0 - SNYGG TEXT) ---")
print("Nu städar vi bort CSS-kod och konstiga tecken.")

filnamn = "riksdagen_protokoll.json"
riksmoten = ["2024%2F25"] 

data_lista = []
unika_id = set()

# Ladda gammal data
if os.path.exists(filnamn):
    with open(filnamn, "r", encoding="utf-8") as f:
        data_lista = json.load(f)
        unika_id = set(rad['dok_id'] for rad in data_lista)

print(f"Startar med {len(data_lista)} protokoll i databasen.")

def stada_html(html_text):
    if not html_text:
        return ""
    
    # 1. Ta bort allt inom <head>...</head> (där ligger ofta titlar och meta-data som vi inte vill ha i brödtexten)
    text = re.sub(r'<head.*?>.*?</head>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. Ta bort allt inom <style>...</style> (Det är detta som skräpade ner din fil!)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 3. Ta bort allt inom <script>...</script>
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 4. Ta bort HTML-kommentarer text = re.sub(r'', '', text, flags=re.DOTALL)

    # 5. Ta bort alla kvarvarande HTML-taggar (<p>, <div>, <br> etc)
    text = re.sub(r'<[^<]+?>', ' ', text) # Ersätt med mellanslag för att inte klistra ihop ord
    
    # 6. Snygga till mellanslag (ta bort dubbla mellanslag, tabbar och nya rader)
    text = " ".join(text.split())
    
    return text

for rm in riksmoten:
    page = 1
    more_pages = True
    
    print(f"\n>>> Hämtar protokoll för {rm.replace('%2F', '/')} <<<")
    
    while more_pages:
        url = f"https://data.riksdagen.se/dokumentlista/?rm={rm}&doktyp=prot&sz=20&p={page}&utformat=json"
        
        try:
            svar = requests.get(url)
            data = svar.json()
            
            if 'dokumentlista' not in data:
                print("Slut på data (ingen lista).")
                break
            
            dokumenten = data['dokumentlista'].get('dokument')
            
            if not dokumenten:
                print(f"Slut på protokoll vid sida {page}.")
                break
                
            if isinstance(dokumenten, dict):
                dokumenten = [dokumenten]

            print(f"Sida {page:<3} (Datum: {dokumenten[0].get('datum', 'Okänt')})... ", end="")
            
            nya_sparade = 0
            
            for dok in dokumenten:
                did = dok['dok_id']
                
                if did not in unika_id:
                    url_html = f"https://data.riksdagen.se/dokument/{did}.html"

                    try:
                        html_svar = requests.get(url_html)
                        if html_svar.status_code == 200:
                            raw = html_svar.text
                            
                            # HÄR ANVÄNDER VI DEN NYA STÄD-FUNKTIONEN
                            ren_text = stada_html(raw)
                            
                            # Extra koll: Om texten blev väldigt kort är det nog något fel
                            if len(ren_text) > 500:
                                sparad_protokoll = {
                                    'dok_id': did,
                                    'titel': dok['titel'],
                                    'datum': dok['datum'],
                                    'typ': 'snabbprotokoll',
                                    'full_text': ren_text
                                }
                                
                                data_lista.append(sparad_protokoll)
                                unika_id.add(did)
                                nya_sparade += 1
                        
                        time.sleep(0.1)
                    except:
                        pass

            print(f"Sparade {nya_sparade} st. (Totalt: {len(data_lista)})")
            
            with open(filnamn, "w", encoding="utf-8") as f:
                json.dump(data_lista, f, indent=4, ensure_ascii=False)
                
            page += 1
            
        except Exception as e:
            print(f"Ett oväntat fel uppstod: {e}")
            break

print(f"\n✅ KLART! {len(data_lista)} städade protokoll sparade.")