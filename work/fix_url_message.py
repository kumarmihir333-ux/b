from pathlib import Path
p=Path('server.py'); s=p.read_text(encoding='utf-8').replace('Use a public HTTPS URL. Feed sources must be RSS or Atom URLs.','Use a public HTTPS URL for the publisher homepage or RSS/Atom feed.'); p.write_text(s,encoding='utf-8')
