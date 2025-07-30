import re

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

top40ou = smogonUsage("stats/gen9ou.txt", top_n=100)
top40uu = smogonUsage("stats/gen9uu.txt",top_n=100)
top40nd = smogonUsage("stats/gen9nationaldex.txt",top_n=100)
print(f'{top40ou} \n\n {top40uu} \n\n {top40nd}')