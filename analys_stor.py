import json

print("--- STOR DATA-ANALYS (1000+ TAL) ---")

# 1. Ladda databasen
filnamn = "riksdagen_host24_framat.json"

try:
    with open(filnamn, "r", encoding="utf-8") as f:
        alla_tal = json.load(f)
        print(f"✅ Läste in {len(alla_tal)} tal från {filnamn}.\n")
except FileNotFoundError:
    print(f"❌ Hittade inte filen '{filnamn}'. Har du kört hämtaren?")
    exit()

# 2. Inställningar för sökord (Vi breddar sökningen rejält)
amnen = {
    "VÅRD": ["vård", "sjukhus", "vårdkö", "omsorg", "cancer", "psykiatri", "primärvård"],
    "GÄNG": ["gäng", "skjutning", "sprängning", "kriminell", "straff", "brottslighet", "polis"],
    "EKONOMI": ["inflation", "ränta", "bolån", "matpris", "budget", "skatt", "tillväxt"],
    "ENERGI": ["elpris", "vindkraft", "kärnkraft", "energi", "bensin", "diesel", "elnät"],
    "FÖRSVAR": ["nato", "ukraina", "ryssland", "försvarsmakt", "militär", "krig"],
    "MIGRATION": ["invandring", "migration", "asyl", "utvisning", "återvandring", "gräns"],
    "SKOLA": ["skola", "betyg", "lärare", "elever", "pisamätning", "skolresultat"],
    "KLIMAT": ["klimat", "utsläpp", "miljö", "reduktionsplikt", "parisavtalet"]
}

partier = ["S", "M", "SD", "C", "V", "KD", "L", "MP"]

# 3. Nollställ räknare
parti_stats = {p: {k: 0 for k in amnen} for p in partier}
talare_stats = {}
total_per_parti = {p: 0 for p in partier}

# 4. Tugga igenom datan
print("🔍 Analyserar textmassorna...")

for tal in alla_tal:
    # Hämta data och städa
    parti = tal.get('parti', '').upper()
    namn = tal.get('talare', 'Okänd')
    text = tal.get('full_text', '').lower()
    
    # Hoppa över talare som inte tillhör riksdagspartierna (t.ex. talmannen ibland)
    if parti not in partier:
        continue

    # Räkna totalt per parti
    total_per_parti[parti] += 1
    
    # Räkna talare
    talare_stats[namn] = talare_stats.get(namn, 0) + 1

    # Kolla ämnen
    for kategori, ordlista in amnen.items():
        # Kolla om något av orden finns i texten
        match = False
        for ordet in ordlista:
            if ordet in text:
                match = True
                break
        if match:
            parti_stats[parti][kategori] += 1

# 5. PRESENTERA RESULTATET

print("\n" + "="*80)
print(f"{'PARTI':<6} {'TOTALT':<8}", end="")
for kat in amnen:
    print(f"{kat[:6]:<8}", end="")
print("\n" + "-"*80)

# Skriv ut tabellen
for parti in partier:
    totalt = total_per_parti[parti]
    print(f"{parti:<6} {totalt:<8}", end="")
    
    for kat in amnen:
        antal = parti_stats[parti][kat]
        # Gör siffran röd om den är hög (över 15% av partiets tal)
        # Detta visar intensitet snarare än bara volym
        visning = str(antal)
        if totalt > 0 and (antal / totalt) > 0.3: # Om ämnet nämns i 30% av talen
            visning = f"🔥{antal}"
            
        print(f"{visning:<8}", end="")
    print() # Ny rad

print("-" * 80)
print("(🔥 = Ämnet dominerar partiets retorik just nu)")

print("\n🏆 TOPP 10 MEST AKTIVA TALARE:")
sorted_talare = sorted(talare_stats.items(), key=lambda x: x[1], reverse=True)
for i, (namn, antal) in enumerate(sorted_talare[:10], 1):
    # Hitta vilket parti talaren tillhör för snyggare lista
    p = "Okänd"
    for t in alla_tal:
        if t.get('talare') == namn:
            p = t.get('parti')
            break
    print(f"{i}. {namn} ({p}): {antal} anföranden")

print("\n")