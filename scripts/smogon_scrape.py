import re
import requests
import json

def pokeSlugify(name):
    name = name.lower().replace(' ', '-').replace('.', '').replace("'", '')
    
    name_x = {
        "ogerpon-wellspring": "ogerpon-wellspring-mask",
        "ogerpon-hearthflame": "ogerpon-hearthflame-mask",
        "ogerpon-cornerstone": "ogerpon-cornerstone-mask",
        "keldeo": "keldeo-ordinary",
        "enamorus": "enamorus-incarnate",
        "indeedee": "indeedee-male",
        "mimikyu": "mimikyu-disguised",
        "maushold": "maushold-family-of-four",
        "basculegion": "basculegion-male",
        "basculegion-f": "basculegion-female",
        "thundurus": "thundurus-incarnate",
        "dundunsparce": "dudunsparce",
        "tatsugiri": "tatsugiri-stretchy",
        "aegislash": "aegislash-shield"
    }
    
    return name_x.get(name, name)

def smogonUsage(path, usage_min=0.0, top_n=None):
    pat = re.compile(r'^\s*\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([\d.]+)%')
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            m = pat.match(line)
            if not m: 
                continue
            name = m.group(1).strip()
            usage = float(m.group(2))
            if usage >= usage_min:
                rows.append((name, usage))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:top_n] if top_n else rows

def getType(name):
    url = f"https://pokeapi.co/api/v2/pokemon/{name.lower()}"
    res = requests.get(url)

    if res.status_code != 200:
        return []

    data = res.json()
    types = [t["type"]["name"].capitalize() for t in data["types"]]
    
    return types

topOU = smogonUsage("stats/gen9ou.txt", top_n=100)
topUU = smogonUsage("stats/gen9uu.txt",top_n=100)
topND = smogonUsage("stats/gen9nationaldex.txt",top_n=100)

topL = []
topL.extend(topOU)
topL.extend(topUU)
topL.extend(topND)

names = [n for n, _ in topL]
unique_names = list(dict.fromkeys(names))

topPoke = {name: getType(slugify(name)) for name in unique_names}
print(topPoke)

with open("jsons/topPoke.json", "w") as f:
    json.dump(topPoke, f, indent=2)

# print(f'{topOU} \n\n {topUU} \n\n {topND}')