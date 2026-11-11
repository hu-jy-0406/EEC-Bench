#!/usr/bin/env python3
import argparse, re
from pathlib import Path
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

def esc(s): return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
def make_story(text, title, font):
    st=getSampleStyleSheet(); st.add(ParagraphStyle(name='T',parent=st['Title'],fontName=font,fontSize=16,leading=21,alignment=TA_CENTER,spaceAfter=12)); st.add(ParagraphStyle(name='B',parent=st['BodyText'],fontName=font,fontSize=9.5,leading=14,spaceAfter=6)); st.add(ParagraphStyle(name='H',parent=st['Heading2'],fontName=font,fontSize=12,leading=16,spaceBefore=8,spaceAfter=5))
    out=[Paragraph(esc(title),st['T'])]
    for raw in text.replace('\r','').split('\n'):
        x=raw.strip()
        if not x: out.append(Spacer(1,3)); continue
        if x.startswith('#'): out.append(Paragraph(esc(x.lstrip('#').strip()),st['H']))
        elif re.match(r'^[-*] ',x): out.append(Paragraph('• '+esc(x[2:]),st['B']))
        else: out.append(Paragraph(esc(x),st['B']))
    return out
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--english',type=Path,required=True); ap.add_argument('--chinese',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
    pdfmetrics.registerFont(TTFont('NotoSC','/tmp/NotoSansSC.ttf'))
    d=SimpleDocTemplate(str(a.out),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=16*mm,bottomMargin=16*mm,title='ICLR 2027 Review — English and Chinese')
    s=make_story(a.english.read_text(),'ICLR 2027 Review — English Original','Helvetica')+[PageBreak()]+make_story(a.chinese.read_text(),'ICLR 2027 Review — Chinese Translation','NotoSC'); d.build(s); print(a.out)
if __name__=='__main__': main()
