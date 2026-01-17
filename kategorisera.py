import json

print("--- PARTIKOLLEN: ÄMNES-ANALYS ---")

# 1. Vi definierar våra "korgar" (ämnen) och vilka ord som hör dit
# Det här är en enkel version av AI. Vi lär datorn synonymer.
amnen = {
    "VÅRD & OMSORG": ["vård", "sjukhus", "patient", "omsorg", "läkare", "sjuksköterska"],
    "LAG & ORDNING": ["polisen", "straff", "brott", "kriminell", "gäng", "skjutning", "fängelse"],
    "ENERGI & MILJÖ": ["kärnkraft", "vindkraft", "elpris", "klimat", "utsläpp", "energi"],
    "EKONOMI": ["skatt", "budget", "bidrag", "inflation", "ränta", "jobb"],
    "FÖRSVAR": ["nato", "försvaret", "militär", "ukraina", "krig", "ryssland"]
}

# 2. Ladda datan
try:
    with open("riksdagen_svar.json", "r", encoding="utf-8") as filen:
        data = json.load(filen)
        alla_tal = data['anforandelista']['anforande']
except:
    print("Ingen data hittades. Kör hamta_data.py först!")
    exit()

# 3. Skapa statistik-tabell (Vem pratar om vad?)
# Struktur: {'S': {'VÅRD': 0, 'LAG': 2}, 'M': {'VÅRD': 1...}}
parti_statistik = {}

print(f"Analyserar {len(alla_tal)} tal mot {len(amnen)} ämnen...\n")

for tal in alla_tal:
    parti = tal['parti'].upper()
    texten = tal.get('full_text', '').lower()
    
    # Om partiet inte finns i statistiken än, lägg till det
    if parti not in parti_statistik:
        parti_statistik[parti] = {kategori: 0 for kategori in amnen}
    
    # Kolla vilket ämne texten handlar om
    hittade_amne = False
    for kategori, nyckelord_lista in amnen.items():
        # Kolla om något av orden finns i texten
        for ordet in nyckelord_lista:
            if ordet in texten:
                # BINGO! Detta tal handlar om denna kategori
                parti_statistik[parti][kategori] += 1
                hittade_amne = True
                
                # Vi skriver ut en träff så du ser att det funkar
                # (Vi tar bara första träffen per tal så vi inte spammar)
                print(f"[{parti}] Talade om {kategori} (ordet '{ordet}' hittades)")
                break # Hoppa till nästa kategori
    
    if not hittade_amne:
        print(f"[{parti}] Talade om 'Övrigt/Okänt'")

# 4. Presentera resultatet snyggt
print("\n" + "="*40)
print("SAMMANSTÄLLNING: VEM PRATAR OM VAD?")
print("="*40)

# Skriv ut rubriker
header = f"{'PARTI':<6}"
for kat in amnen:
    header += f" {kat[:4]:<5}" # Vi kortar ner 'VÅRD & OMSORG' till 'VÅRD' för att få plats
print(header)
print("-" * 40)

for parti, stats in parti_statistik.items():
    rad = f"{parti:<6}"
    for antal in stats.values():
        rad += f" {antal:<5}"
    print(rad)

print("\n(Siffrorna visar antal tal där ämnet nämndes)")