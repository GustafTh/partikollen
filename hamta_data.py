import requests
import json
import time
import re # "Städpatrullen" som tvättar bort kod

# Vi hämtar listan
url_lista = "https://data.riksdagen.se/anforandelista/?rm=2023%2F24&sz=50&utformat=json"

print("1. Hämtar lista...")
svar = requests.get(url_lista)
data = svar.json()
lista_med_tal = data['anforandelista']['anforande']
berikad_lista = []

print(f"Hittade {len(lista_med_tal)} tal. Nu hämtar vi innehållet som ren text...")

count = 0
for rad in lista_med_tal:
    if count >= 100:
        break

    # Vi använder länken EXAKT som den är, vi ändrar inget
    url = rad['anforande_url_xml']
    
    print(f"\n--- Hämtar: {rad['talare']} ---")
    
    try:
        # Vi hämtar sidan
        svar_text = requests.get(url)
        
        if svar_text.status_code == 200:
            # Vi tar innehållet som TEXT (inte JSON)
            rad_data = svar_text.text
            
            # STÄDPATRULLEN:
            # 1. Ta bort allt som ser ut som <taggar>
            ren_text = re.sub('<[^<]+?>', '', rad_data)
            # 2. Ta bort konstiga tecken som &nbsp; (mellanslag)
            ren_text = ren_text.replace("&nbsp;", " ").replace("\r", " ").replace("\n", " ")
            # 3. Ta bort dubbla mellanslag
            ren_text = " ".join(ren_text.split())
            
            # Vi kollar om vi fick ut något vettigt
            if len(ren_text) > 100:
                print(f" -> BINGO! Hittade text ({len(ren_text)} tecken).")
                rad['full_text'] = ren_text
                berikad_lista.append(rad)
                count += 1
            else:
                print(" -> Texten blev för kort efter städning.")
        else:
            print(f" -> Felkod från servern: {svar_text.status_code}")
            
        time.sleep(0.5)

    except Exception as e:
        print(f" -> Något gick snett: {e}")

# Spara
with open("riksdagen_svar.json", "w", encoding="utf-8") as filen:
    json.dump({'anforandelista': {'anforande': berikad_lista}}, filen, indent=4, ensure_ascii=False)

print(f"\nKlart! Sparade {len(berikad_lista)} tal.")