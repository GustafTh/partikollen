import requests
import json
import time
import re
import os
import sys

# Fixar teckenkodning
sys.stdout.reconfigure(encoding='utf-8')

print("--- VOTERINGS-HÄMTAREN ---")
print("Hämtar beslut och omröstningar från riksdagen.")

filnamn = "riksdagen_voteringar.json"
riksmoten = ["2024%2F25"] 

data_lista = []
unika_id = set()

# Ladda gammal data om den finns
if os.path.exists(filnamn):
    with open(filnamn, "r", encoding="utf-8") as f:
        data_lista = json.load(f)
        unika_id = set(rad['dok_id'] for rad in data_lista)

print(f"Startar med {len(data_lista)} voteringar i databasen.")

# --- TVÄTTMASKIN (Special för tabeller) ---
def stada_html(html_text):
    if not html_text:
        return ""
    
    # För voteringar är det viktigt att hantera tabeller snyggt
    # Vi byter ut slut-taggen på celler (</td>) mot ett mellanslag
    # så att "Ja: 50" inte blir "Ja:50"
    html_text = html_text.replace("</td>", " ").replace("</th>", " ")
    html_text = html_text.replace("</tr>", "\n") # Ny rad vid ny tabellrad

    # Standardstädning
    text = re.sub(r'<head.*?>.*?</head>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^<]+?>', ' ', text) # Ta bort resterande taggar
    
    # Snygga till mellanslag
    text = " ".join(text.split())
    return text

# --- HUVUDLOOP ---
for rm in riksmoten:
    page = 1
    more_pages = True
    
    print(f"\n>>> Hämtar voteringar (vot) för {rm.replace('%2F', '/')} <<<")
    
    while more_pages:
        # doktyp=vot är koden för voteringar
        url = f"https://data.riksdagen.se/dokumentlista/?rm={rm}&doktyp=vot&sz=50&p={page}&utformat=json"
        
        try:
            svar = requests.get(url)
            data = svar.json()
            
            if 'dokumentlista' not in data:
                print("Slut på data.")
                break
            
            dokumenten = data['dokumentlista'].get('dokument')
            
            if not dokumenten:
                print(f"Slut på voteringar vid sida {page}.")
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
                            
                            # Tvätta texten
                            ren_text = stada_html(raw)
                            
                            sparad_dok = {
                                'dok_id': did,
                                'titel': dok['titel'],
                                'datum': dok['datum'],
                                'typ': 'votering',
                                'subtyp': dok.get('subtyp', ''),
                                'beslut': dok.get('beslut', '?'), # Ibland finns beslut direkt i listan
                                'full_text': ren_text
                            }
                            
                            data_lista.append(sparad_dok)
                            unika_id.add(did)
                            nya_sparade += 1
                        
                        time.sleep(0.05)
                    except:
                        pass

            print(f"Sparade {nya_sparade} st. (Totalt: {len(data_lista)})")
            
            with open(filnamn, "w", encoding="utf-8") as f:
                json.dump(data_lista, f, indent=4, ensure_ascii=False)
                
            page += 1
            
        except Exception as e:
            print(f"Fel: {e}")
            page += 1
            time.sleep(2)

print(f"\n✅ KLART! Voteringar sparade i '{filnamn}'.")