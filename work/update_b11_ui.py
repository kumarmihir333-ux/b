from pathlib import Path
p=Path('app.js')
s=p.read_text(encoding='utf-8')
repls={
"signals:{crumb:'Signals & archive',eyebrow:'SOURCE INTELLIGENCE',title:'See what’s changing.',desc:'Follow live source feeds, search captured reporting, and trace each headline back to its publisher.',body:signalsPage}":"signals:{crumb:'B11 source monitor',eyebrow:'B11 · PUBLIC SOURCE SCOUT',title:'Follow public reporting with B11.',desc:'B11 checks registered publisher feeds, keeps source links visible, and helps you spot new coverage for human review.',body:signalsPage}",
"Signals &amp; archive <span class=\"nav-tag\">LIVE</span>":"B11 source monitor <span class=\"nav-tag\">LIVE</span>",
"Connecting to source desk…":"Connecting to B11…",
"Checking local archive":"Checking registered public feeds",
"id=\"refreshSignals\">↻ Refresh feeds":"id=\"refreshSignals\">↻ Run B11 scan",
"<option value=\"feed\">RSS / Atom feed</option><option value=\"bookmark\">Web page bookmark</option>":"<option value=\"feed\">Public feed or publisher homepage</option><option value=\"bookmark\">Bookmark a web page</option>",
"Feeds are checked only when you refresh. Bookmarks are saved for reference.":"Add a public publisher homepage or RSS/Atom URL. B11 tries feed discovery on homepages; bookmarks are reference-only.",
"Reading configured feeds and local archive…":"B11 is checking registered public RSS/Atom feeds…",
"signalStatus('online','Source desk connected',`Local archive ready · ${health.sources} sources · ${health.stories} captures`);":"signalStatus('online','B11 is connected',`Local archive ready · ${health.sources} registered sources · ${health.stories} captured items`);",
"Source added. Refresh feeds to capture available items.":"Source added. Run B11 scan to capture available feed items.",
"toast('Source added to registry.')":"toast('Source added for B11 to monitor.')",
"Publisher pages remain the source of record. M11 archives feed metadata and links, not full newspaper articles.":"B11 checks public RSS/Atom feeds from sources you register. Paste a publisher homepage and it will try to discover its feed. It does not crawl every page or bypass paywalls. M11 stores feed headlines, excerpts, dates, and links, not full newspaper articles."
}
for old,new in repls.items():
    if old not in s: print('MISSING:',old[:100])
    s=s.replace(old,new)
p.write_text(s,encoding='utf-8')

p=Path('README.md'); s=p.read_text(encoding='utf-8')
s=s.replace('In **Signals & archive**, refresh feeds to collect recent items. Connected feeds refresh every five minutes while that page is open. The SQLite archive persists on this computer.','In **B11 source monitor**, add public publisher homepages or RSS/Atom feed URLs, then run a scan to collect recent items. B11 tries RSS/Atom autodiscovery when given a homepage and checks only the sources you register. Connected feeds refresh every five minutes while that page is open. The SQLite archive persists on this computer.')
s=s.replace('The feed reader stores publisher-provided headlines, feed excerpts, publication dates, and source links. It does not scrape or copy full newspaper articles.','B11 reads registered public RSS/Atom feeds, including feeds discovered from publisher homepage metadata. It stores publisher-provided headlines, excerpts, publication dates, and source links. It does not crawl whole sites, bypass access controls, or scrape and copy full newspaper articles.')
s=s.replace('- Signals & archive: RSS/Atom refresh, source registry, search, recent coverage, older captures, and a source-to-headline map.','- B11 source monitor: registered public RSS/Atom refresh, homepage feed autodiscovery, source registry, search, recent coverage, older captures, and a source-to-headline map.')
s=s.replace('The source service is local and RSS/Atom based, and is not a public production service.','B11 currently scans only registered RSS/Atom sources; a publisher homepage works only when it advertises a feed. The source service is local and is not a public production service.')
p.write_text(s,encoding='utf-8')
