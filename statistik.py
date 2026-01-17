import json

print("--- ANALYSERAR 150 TAL FRÅN RIKSDAGEN ---")

# 1. Ladda din stora databas
filnamn = "riksdagen_stor_data.json"
try:
    with open(filnamn, "r", encoding="utf-8") as f:
        alla_tal = json.load(f)
except:
    print(f"Hittade inte filen {filnamn}. Kör mass_hamtare.py först!")
    exit()

print(f"Läste in {len(alla_tal)} anföranden. Nu räknar vi...\n")

# 2. Definiera ämnen och nyckelord (Lite mer avancerad lista)
amnen = {
    "VÅRD": ["vård", "sjukhus", "patient", "omsorg", "köer", "cancer", "sjuksköterska"],
    "BROTT": ["polisen", "straff", "brott", "kriminell", "gäng", "skjutning", "fängelse", "trygghet"],
    "ENERGI": ["kärnkraft", "vindkraft", "elpris", "klimat", "utsläpp", "energi", "bensin", "diesel"],
    "EKONOMI": ["skatt", "budget", "bidrag", "inflation", "ränta", "jobb", "företag", "tillväxt"],
    "FÖRSVAR": ["nato", "försvaret", "militär", "ukraina", "krig", "ryssland", "säkerhet"],
    "SKOLA": ["skola", "elever", "lärare", "betyg", "utbildning", "pisamätning"],
    "MIGRATION": ["migration", "invandring", "asyl", "uppehållstillstånd", "utvisning", "sfi"]
}

# 3. Nollställ räkneverket
# Vi bygger en struktur: statistik['S']['VÅRD'] = 5
partier = ["S", "M", "SD", "C", "V", "KD", "L", "MP"]
statistik = {p: {k: 0 for k in amnen} for p in partier}
statistik["ÖVRIGA"] = {k: 0 for k in amnen} # För oberoende vildar

talare_topplista = {}

# 4. Analysera varje tal
for tal in alla_tal:
    parti = tal['parti'].upper()
    if parti not in statistik:
        parti = "ÖVRIGA"
        
    texten = tal.get('full_text', '').lower()
    namn = tal['talare']
    
    # Räkna talare (Vem pratar mest?)
    talare_topplista[namn] = talare_topplista.get(namn, 0) + 1

    # Kolla ämnen
    for kategori, ordlista in amnen.items():
        for ordet in ordlista:
            if ordet in texten:
                statistik[parti][kategori] += 1
                break # En träff per kategori räcker per tal

# 5. PRESENTERA RESULTATET

# --- TABELLEN ---
print(f"{'PARTI':<8}", end="")
for kat in amnen:
    print(f"{kat[:5]:<7}", end="")
print("TOTALT")
print("-" * 70)

for parti in partier:
    print(f"{parti:<8}", end="")
    total_hits = 0
    for kat in amnen:
        antal = statistik[parti][kat]
        total_hits += antal
        # Om siffran är 0, visa ett streck istället för renlighet
        visning = str(antal) if antal > 0 else "-"
        print(f"{visning:<7}", end="")
    print(f" {total_hits}")

print("-" * 70)
print("\n")

# --- TOPPLISTOR ---
print("🏆 MEST AKTIVA TALARE:")
# Sortera talarna och ta topp 5
sorterade_talare = sorted(talare_topplista.items(), key=lambda x: x[1], reverse=True)
for i, (namn, antal) in enumerate(sorterade_talare[:5], 1):
    print(f"{i}. {namn}: {antal} anföranden")

print("\n🔥 HETASTE ÄMNET JUST NU:")
amnes_total = {k: 0 for k in amnen}
for p in statistik:
    for k in amnen:
        amnes_total[k] += statistik[p][k]
        
vinnare_amne = max(amnes_total, key=amnes_total.get)
print(f"Det pratas mest om: {vinnare_amne} ({amnes_total[vinnare_amne]} träffar)")