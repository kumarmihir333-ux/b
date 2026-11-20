import re
from pathlib import Path
p=Path('index.html'); s=p.read_text(encoding='utf-8'); s,n=re.subn(r'Signals &amp;\s*archive', 'B11 source monitor', s); print('nav replacements',n); p.write_text(s,encoding='utf-8')
