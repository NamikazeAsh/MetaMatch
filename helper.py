def pokeSlugify(name):
    name = name.lower().replace(' ', '-').replace('.', '').replace("'", '').replace(':', '')
    
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
        "tornadus": "tornadus-incarnate",
        "landorus": "landorus-incarnate",
        "aegislash": "aegislash-shield",
        "pumpkaboo": "pumpkaboo-average",
        "gourgeist": "gourgeist-average",
        "zygarde": "zygarde-50",
        "oricorio": "oricorio-baile",
        "lycanroc": "lycanroc-midday",
        "wishiwashi": "wishiwashi-solo",
        "minior": "minior-red-meteor",
        "urshifu": "urshifu-single-strike",
        
        "tatsugiri": "tatsugiri-stretchy",
    }
    
    return name_x.get(name, name)
