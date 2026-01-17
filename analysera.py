import json

# En liten funktion för att ta bort HTML-taggar (som <p> och </p>)
def stada_text(text):
    if text is None: return "Ingen text."
    return text.replace("<p>", "").replace("</p>", "\n").replace("<em>", "").replace("</em>", "")

with open("riksdagen_svar.json", "r", encoding="utf-8") as filen:
    data = json.load(filen)

alla_tal = data['anforandelista']['anforande']

for tal in alla_tal:
    parti = tal['parti']
    namn = tal['talare']
    
    # Här hämtar vi den nya texten vi laddade ner!
    texten = stada_text(tal.get('full_text', 'Saknas'))
    
    # Vi visar bara de första 200 bokstäverna, så skärmen inte svämmar över
    kort_text = texten[0:200] 

    print(f"TALARE: {namn} ({parti})")
    print(f"SA TILL RIKSDAGEN:")
    print("-" * 20)
    print(f"{kort_text}...") # Lägger till ... på slutet
    print("-" * 20)
    print("\n") # Lite extra luft