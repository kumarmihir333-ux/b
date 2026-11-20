from pathlib import Path
p=Path('index.html'); s=p.read_text(encoding='utf-8').replace('Signals &amp; \narchive <span class="nav-tag">LIVE</span>','B11 source monitor <span class="nav-tag">LIVE</span>'); p.write_text(s,encoding='utf-8')
p=Path('app.js'); s=p.read_text(encoding='utf-8')
s=s.replace("signalStatus('loading','Connecting to source desk'", "signalStatus('loading','B11 is scanning sources'")
s=s.replace("signalStatus('online','Source desk connected',`Local archive ready · ${health.sources} sources · ${health.stories} captures`)", "signalStatus('online','B11 is connected',`Local archive ready · ${health.sources} registered sources · ${health.stories} captures`)")
s=s.replace('The service fetches RSS/Atom feeds and saves headline history to a local SQLite archive.','B11 reads registered public RSS/Atom feeds and saves source-linked headlines to the local SQLite archive.')
s=s.replace("message.textContent='Source added. Run B11 scan to capture available feed items.';toast('Source added for B11 to monitor.');", "message.textContent=data.kind==='feed'?'Source added. B11 will try this homepage or feed URL when you scan.':'Bookmark saved for reference; B11 does not scan bookmarks.';toast(data.kind==='feed'?'Source added for B11 to monitor.':'Bookmark saved.');")
p.write_text(s,encoding='utf-8')
