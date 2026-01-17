import json

print("--- PARTIKOLLENS SÖKMOTOR ---")

# 1. Ladda databasen
try:
    with open("riksdagen_svar.json", "r", encoding="utf-8") as filen:
        data = json.load(filen)
        alla_tal = data['anforandelista']['anforande']
except:
    print("Hittade ingen datafil. Kör hamta_data.py först!")
    exit()

while True:
    print("\n" + "="*30)
    keyword = input("Vad vill du söka efter? (skriv 'q' för att avsluta): ").lower()
    
    if keyword == 'q':
        break
    
    print(f"Letar efter '{keyword}' i {len(alla_tal)} tal...\n")
    
    traffar = 0
    
    for tal in alla_tal:
        # Hämta texten och gör den till små bokstäver (för sökningens skull)
        texten = tal.get('full_text', '').lower()
        parti = tal['parti']
        namn = tal['talare']
        datum = tal['dok_datum']
        
        if keyword in texten:
            traffar += 1
            # Hitta var ordet står för att visa ett smakprov
            index = texten.find(keyword)
            # Vi klipper ut lite text runt ordet (50 tecken före och efter)
            start = max(0, index - 50)
            slut = min(len(texten), index + 100)
            smakprov = texten[start:slut].replace("\n", " ")
            
            print(f"🟢 TRÄFF: {namn} ({parti}) - {datum}")
            print(f"   \"...{smakprov}...\"")
            print("-" * 20)

    if traffar == 0:
        print("❌ Ingen pratade om detta i de tal du hämtat.")
    else:
        print(f"Totalt {traffar} träffar.")