from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.pdfbase.pdfmetrics import stringWidth
from pathlib import Path

out = Path(r'C:\Users\ADMIN\Documents\Codex\2026-11-20\b\outputs\M11_Bihar_Intelligence_Guide.pdf')
out.parent.mkdir(parents=True, exist_ok=True)

NAVY = colors.HexColor('#10172D')
INK = colors.HexColor('#19233D')
MUTED = colors.HexColor('#5D6880')
GOLD = colors.HexColor('#E9B949')
TEAL = colors.HexColor('#3AAE9B')
CORAL = colors.HexColor('#E66F5C')
PALE = colors.HexColor('#F3F5F8')
LINE = colors.HexColor('#DCE2EB')
WHITE = colors.white

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='CoverTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=30, leading=35, textColor=NAVY, alignment=TA_LEFT, spaceAfter=12))
styles.add(ParagraphStyle(name='CoverSub', parent=styles['Normal'], fontName='Helvetica', fontSize=12, leading=18, textColor=MUTED, spaceAfter=14))
styles.add(ParagraphStyle(name='Section', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=21, leading=26, textColor=NAVY, spaceBefore=2, spaceAfter=12))
styles.add(ParagraphStyle(name='Subhead', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=15, textColor=NAVY, spaceBefore=7, spaceAfter=5))
styles.add(ParagraphStyle(name='BodyM', parent=styles['BodyText'], fontName='Helvetica', fontSize=9.5, leading=14, textColor=INK, spaceAfter=6))
styles.add(ParagraphStyle(name='SmallM', parent=styles['BodyText'], fontName='Helvetica', fontSize=8.2, leading=11, textColor=MUTED, spaceAfter=3))
styles.add(ParagraphStyle(name='CardTitle', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=10, leading=13, textColor=NAVY, spaceAfter=4))
styles.add(ParagraphStyle(name='WhiteTitle', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=WHITE, spaceAfter=5))
styles.add(ParagraphStyle(name='WhiteBody', parent=styles['BodyText'], fontName='Helvetica', fontSize=9, leading=13, textColor=colors.HexColor('#E6EAF3')))
styles.add(ParagraphStyle(name='StepNum', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=14, leading=16, textColor=TEAL, alignment=TA_CENTER))

W, H = letter

def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor('#FBFCFE'))
    canvas.rect(0, 0, W, H, stroke=0, fill=1)
    canvas.setFillColor(NAVY)
    canvas.rect(0, H-0.16*inch, W, 0.16*inch, stroke=0, fill=1)
    canvas.setFillColor(GOLD)
    canvas.rect(0, H-0.16*inch, 1.65*inch, 0.16*inch, stroke=0, fill=1)
    if doc.page > 1:
        canvas.setFont('Helvetica-Bold', 8)
        canvas.setFillColor(NAVY)
        canvas.drawString(0.62*inch, H-0.43*inch, 'M11  /  BIHAR DEVELOPMENT INTELLIGENCE')
        canvas.setStrokeColor(LINE)
        canvas.line(0.62*inch, H-0.52*inch, W-0.62*inch, H-0.52*inch)
    canvas.setStrokeColor(LINE)
    canvas.line(0.62*inch, 0.48*inch, W-0.62*inch, 0.48*inch)
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.62*inch, 0.30*inch, 'M11 - evidence-led exploration, with human review')
    canvas.drawRightString(W-0.62*inch, 0.30*inch, f'{doc.page}')
    canvas.restoreState()

def P(txt, style='BodyM'):
    return Paragraph(txt, styles[style])

def card(title, body, accent=TEAL, width=2.25*inch):
    data=[[P(title,'CardTitle')],[P(body,'SmallM')]]
    t=Table(data, colWidths=[width])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),WHITE),('BOX',(0,0),(-1,-1),0.7,LINE),
        ('LINEBEFORE',(0,0),(0,-1),3,accent),('LEFTPADDING',(0,0),(-1,-1),11),
        ('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,0),9),
        ('BOTTOMPADDING',(0,0),(-1,0),2),('TOPPADDING',(0,1),(-1,1),1),
        ('BOTTOMPADDING',(0,1),(-1,1),9),
    ]))
    return t

story=[]
story += [Spacer(1,0.55*inch), P('M11', 'Section')]
story += [P('A Bihar development<br/>intelligence workspace','CoverTitle')]
story += [P('A practical guide to exploring development data, tracking sources, spotting unusual changes, and organizing evidence about events across Bihar.','CoverSub')]

hero=Table([[P('FROM SIGNAL TO REVIEW','WhiteTitle'), P('A clear workflow for analysts','WhiteTitle')],
            [P('Bring together sourced observations and public feed items. Keep the evidence visible as you explore a change.','WhiteBody'),
             P('M11 helps a person investigate what may be happening. It does not verify an event or make decisions on its own.','WhiteBody')]], colWidths=[3.25*inch,3.25*inch])
hero.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),NAVY),('BOX',(0,0),(-1,-1),0,NAVY),('INNERGRID',(0,0),(-1,-1),0.5,colors.HexColor('#36415D')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),14),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
story += [hero, Spacer(1,15), P('What M11 is for','Subhead'), P('M11 is a prototype workspace for Bihar-focused research and development intelligence. It brings source management, district data, pattern scans, event analysis, an evidence graph, and report drafting into one place. Its aim is to help a researcher move from a question to a traceable review of evidence.','BodyM')]

cards=Table([[card('Explore','Browse available sources, indicators, district coverage, and captured headlines.',GOLD,2.1*inch),card('Check','Review imported data, compare periods, and inspect pattern signals.',TEAL,2.1*inch),card('Explain','Record evidence, assumptions, alternative hypotheses, and next checks.',CORAL,2.1*inch)]], colWidths=[2.18*inch,2.18*inch,2.18*inch])
cards.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),7)]))
story += [cards, Spacer(1,11), P('Who can use it','Subhead'), P('Researchers, civil-society teams, journalists, policy analysts, and development practitioners can use M11 to organize public information and identify questions for follow-up. A reviewer should verify important findings against the original sources.','BodyM')]
story += [PageBreak()]

story += [Spacer(1,0.18*inch), P('How to use M11','Section'), P('A careful workflow keeps source quality and human review at the center.','CoverSub')]
steps=[
('1','Start with a question','Choose a district, topic, indicator, or event you want to understand.'),
('2','Check the source','Open the source record and note publisher, date, link, reporting period, and coverage.'),
('3','Add data carefully','Import an authorized CSV when needed. Imported rows remain pending until a person reviews and approves them.'),
('4','Explore patterns','Use the pattern engine to scan a time series. Read the matching rule and dates; a pattern is a prompt to investigate, not proof.'),
('5','Assess an event','Use Event Analysis to record claims, source links, hypotheses, assumptions, confidence, and what evidence could change the assessment.'),
('6','Share a draft','Use Report Studio to prepare a sourced Markdown draft. Review every statement and link before sharing.')]
for n,title,body in steps:
    row=Table([[P(n,'StepNum'),[P(title,'CardTitle'),P(body,'BodyM')]]],colWidths=[0.48*inch,5.95*inch])
    row.setStyle(TableStyle([('BACKGROUND',(0,0),(0,0),PALE),('BOX',(0,0),(-1,-1),0.5,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story += [row,Spacer(1,6)]
story += [Spacer(1,2), P('Current access and data note','Subhead'), P('The public GitHub Pages version hosts the interface. The Python service and SQLite archive are local-only at present, so shared live data collection, imports, reviews, and radar scans require the local service. Start it with <b>python server.py</b> in the project folder, then open <b>http://localhost:8000</b>. The public page alone does not connect to that local database.','BodyM')]
story += [PageBreak()]

story += [Spacer(1,0.18*inch), P('Three ways to use it','Section'), P('These are illustrative workflows, not current alerts or claims about conditions in Bihar.','CoverSub')]
examples=[
('01  |  Review a possible flood-related change','A researcher imports dated rainfall, river-level, or affected-area observations from an authorized source. After review, they compare district timelines, inspect a radar pin if one qualifies, and record which official bulletin or field report should be checked next.'),
('02  |  Investigate a district service gap','A development team brings in comparable district-level measures, such as service availability over multiple periods. They check definitions and missing districts, compare trends, then use Event Analysis to separate the measured gap from possible explanations such as access, staffing, or reporting changes.'),
('03  |  Understand a sudden shift in a public indicator','An analyst notices a sharp change in a time series, such as a price, health, or education measure. The pattern engine helps locate the unusual period; source links and news headlines provide context. The analyst compares explanations and documents what additional evidence would confirm or weaken them.')]
for title,body in examples:
    story += [KeepTogether([card(title,body,GOLD,6.35*inch),Spacer(1,9)])]

wip=Table([[P('WORK IN PROGRESS','WhiteTitle')],[P('<b>B11:</b> a planned named analysis agent that could help coordinate source-backed findings from M11 tools. It is a concept for future development and is not currently active in the site. Other future work includes a secure shared backend, accounts and permissions, scheduled authorized data connectors, more district time series, and Hindi support.','WhiteBody')]],colWidths=[6.35*inch])
wip.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),NAVY),('LEFTPADDING',(0,0),(-1,-1),13),('RIGHTPADDING',(0,0),(-1,-1),13),('TOPPADDING',(0,0),(-1,0),10),('BOTTOMPADDING',(0,0),(-1,0),3),('TOPPADDING',(0,1),(-1,1),2),('BOTTOMPADDING',(0,1),(-1,1),11)]))
story += [Spacer(1,2),wip,Spacer(1,9),P('Important limitations','Subhead'),P('The radar analyzes approved numeric observations and uses a transparent heuristic score. It needs at least five comparable dated periods to establish a baseline and detect a new value. Direction labels require explicit metadata; otherwise results stay unclassified. Pattern matches and recommendations are leads for human review, not predictions, diagnoses, or proof of cause. Feed capture stores publisher headlines and excerpts, not a complete newspaper archive.','SmallM'),P('Website: https://kumarmihir333-ux.github.io/b/','SmallM')]

doc=SimpleDocTemplate(str(out),pagesize=letter,rightMargin=0.62*inch,leftMargin=0.62*inch,topMargin=0.70*inch,bottomMargin=0.67*inch,title='M11 - Bihar Development Intelligence Guide',author='M11 AI')
doc.build(story,onFirstPage=on_page,onLaterPages=on_page)
print(out)
