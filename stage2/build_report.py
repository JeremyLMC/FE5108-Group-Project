"""Build the four-page Stage 2 report from reproduced CSVs (ReportLab)."""
from pathlib import Path
import json
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

BASE = Path(__file__).resolve().parent
OUT = BASE/'reports/Stage2_CAPM_Report.pdf'
OUT.parent.mkdir(exist_ok=True)
# Prefer a portable bundled font when this script runs outside macOS.
font_candidates = [Path('/System/Library/Fonts/Supplemental'),
                   Path('/usr/share/fonts/truetype/liberation2')]
for folder in font_candidates:
    regular = folder/'Arial.ttf' if (folder/'Arial.ttf').exists() else folder/'LiberationSans-Regular.ttf'
    bold = folder/'Arial Bold.ttf' if (folder/'Arial Bold.ttf').exists() else folder/'LiberationSans-Bold.ttf'
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont('Body', str(regular)))
        pdfmetrics.registerFont(TTFont('BodyBold', str(bold)))
        pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='Body',boldItalic='BodyBold')
        break
else:
    pdfmetrics.registerFontFamily('Helvetica',normal='Helvetica',bold='Helvetica-Bold',italic='Helvetica-Oblique',boldItalic='Helvetica-BoldOblique')
FONT = 'Body' if 'Body' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
BOLD = 'BodyBold' if FONT == 'Body' else 'Helvetica-Bold'
body = ParagraphStyle('Body',fontName=FONT,fontSize=10,leading=13.4,spaceAfter=8)
small = ParagraphStyle('Small',parent=body,fontSize=8.2,leading=10.4)
heading = ParagraphStyle('Heading',parent=body,fontName=BOLD,fontSize=13,leading=16)
caption = ParagraphStyle('Caption',parent=body,fontName=BOLD,fontSize=9,leading=11.5)
capm = pd.read_csv(BASE/'results/capm_results.csv')
s = json.loads((BASE/'results/stage2_summary.json').read_text())
c = canvas.Canvas(str(OUT),pagesize=(612,792))
c.setTitle('Stage 2 The CAPM');c.setAuthor('FE5108 Group Project')
LEFT, WIDTH, y = 54, 504, 730

def start(page, title=None):
    global y
    c.setFont(FONT,8);c.drawString(54,764,'FE5108  |  Group project  |  Stage 2')
    c.drawRightString(558,28,f'Stage 2  |  {page}')
    y=730
    if title:
        c.setFont(BOLD,18);c.drawString(LEFT,y,title);y-=29

def para(text, style=body, gap=8):
    global y
    p=Paragraph(text,style);w,h=p.wrap(WIDTH,700)
    assert y-h>=49, f'Page overflow at {text[:60]}, y={y}, height={h}'
    p.drawOn(c,LEFT,y-h);y-=h+gap

def h(text):para(text,heading,7)
def table(headers, rows, widths=None, fontsize=9, shades=False):
    global y
    data=[headers]+rows
    t=Table(data,colWidths=widths or [WIDTH/len(headers)]*len(headers))
    cmds=[('FONTNAME',(0,0),(-1,-1),FONT),('FONTNAME',(0,0),(-1,0),BOLD),
          ('FONTSIZE',(0,0),(-1,-1),fontsize),('LEADING',(0,0),(-1,-1),fontsize+2),
          ('BACKGROUND',(0,0),(-1,0),HexColor('#E6EBEF')),('GRID',(0,0),(-1,-1),.3,HexColor('#D2D2D2')),
          ('ALIGN',(0,0),(-1,-1),'RIGHT'),('ALIGN',(0,0),(0,-1),'LEFT'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
          ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]
    for i,row in enumerate(rows,1):
        tint='#FFF1D6' if shades and row[0] in {'GE','XOM','PFE','RTX','INTC','VZ'} else '#EDF3F9'
        cmds.append(('BACKGROUND',(0,i),(-1,i),HexColor(tint)))
        if len(headers)==10:
            for col in [0,5]:
                if row[col] in {'GE','XOM','PFE','RTX','INTC','VZ'}:
                    cmds.append(('BACKGROUND',(col,i),(col+4,i),HexColor('#FFF1D6')))
    t.setStyle(TableStyle(cmds));_,height=t.wrap(WIDTH,700)
    assert y-height>=49, f'Table overflow: {height} at {y}'
    t.drawOn(c,LEFT,y-height);y-=height+9

start(1,'Stage 2 The CAPM')
h('Introduction')
para('We test whether market exposure explains returns for the same 29-stock historical Dow Jones universe used in Stage 1. The fitted Security Market Line (SML) is flatter than the CAPM benchmark, with a positive intercept. Three individual alphas exceed the approximate significance threshold, but that count alone does not establish a joint rejection.')
para('We retain 130 monthly USD observations from November 2015 to August 2026. Stock returns use the frozen Stage 1 panel, including its spin-off reinvestment convention. The risk-free proxy is the Kenneth French one-month Treasury-bill return; the market proxy is the French broad US equity market excess return. This proxy covers a broader equity opportunity set than our 29 stocks, but does not represent all investable wealth.')
h('2a Security characteristic regressions')
para('For each stock, ordinary least squares estimates the security characteristic regression:',gap=4)
para('<b>Ri,t - Rf,t = alpha_i + beta_i x (RM,t - Rf,t) + error_i,t</b>',gap=4)
para('The dependent variable subtracts that month\'s RF once; Mkt-RF is already an excess return. Inputs are decimal monthly returns. Conventional OLS standard errors produce the alpha t statistics.',gap=6)
para('Table 2.1 CAPM estimates for all 29 stocks',caption,4)
rows=[]
for r in capm.itertuples():
    rows.append([r.Ticker,f'{r.Beta:.4f}',f'{100*r.Alpha_monthly:.3f}',f'{r.t_Alpha:.3f}',f'{r.R_squared:.3f}'])
paired=[rows[i]+(rows[i+15] if i+15<len(rows) else ['','','','','']) for i in range(15)]
table(['Stock','Beta','Alpha %','t alpha','R sq.']*2,paired,[40,52,58,52,50]*2,8.2)
para('All regressions use 130 months. Blue rows identify retained DJIA members; amber marks later index removals. R squared measures time-series fit, not whether expected returns satisfy the CAPM. Old DuPont is excluded for the Stage 1 historical data gap; UTX continues as RTX.',small,0)
c.showPage()

start(2)
h('2b The empirical Security Market Line')
para('The CAPM predicts that an asset\'s expected excess return equals its beta times the market risk premium. We replace expectations with sample arithmetic monthly means and plot each stock\'s mean excess return against its estimated beta. A cross-sectional OLS regression fits <b>mean excess return = intercept + slope x estimated beta</b> across the 29 stocks. This fitted line is distinct from the 29 time-series regressions in Table 2.1.')
para('The theoretical line goes through the origin because the vertical axis is excess return. Its slope is the sample mean of Mkt-RF, 1.064% per month. The Treasury-bill mean is not an additional intercept in this space. All stock and market means use the same 130 months.',gap=9)
im=Image(str(BASE/'figures/empirical_sml.png'),width=504,height=285.6)
im.drawOn(c,LEFT,y-285.6);y-=294
para('Figure 2.1 The empirical SML rises more slowly than the theoretical line, while individual stocks show substantial dispersion around both lines.',caption,9)
para('Table 2.2 Fitted and theoretical SML parameters',caption,4)
table(['Line','Intercept % monthly','Slope % monthly'],[
    ['Empirical fitted SML',f'{100*s["empirical_intercept"]:.3f}',f'{100*s["empirical_slope"]:.3f}'],
    ['Theoretical CAPM SML','0.000',f'{100*s["theoretical_slope"]:.3f}']],[220,142,142])
para('The fitted cross-sectional R squared is 0.133: beta explains about 13.3% of the variation in realized mean excess returns across these stocks. This is not the time-series R squared in Table 2.1 and does not by itself test the pricing restrictions.')
para('For example, CAT has a mean excess return of 2.286% with beta 1.240, whereas NKE has -0.139% with beta 0.943. The scatter illustrates why beta alone provides an incomplete description of this sample\'s realized mean returns. Section 2d compares the two lines in economic terms.')
c.showPage()

start(3)
h('2c A joint assessment of zero alphas')
para('The CAPM restriction is that every asset\'s population alpha is zero. We assess that restriction using the handout\'s permitted chance-count discussion, rather than a formal Gibbons-Ross-Shanken (GRS) test. Individual significance is useful for identifying stocks to investigate, but does not by itself establish whether all alphas are jointly different from zero.')
para('For each stock, we compare its estimated alpha with its conventional OLS standard error. The handout\'s rule |t(alpha)| &gt; 2 approximates a two-sided 5% test. With 130 observations and two estimated coefficients, each regression has 128 residual degrees of freedom. Exact p values and the approximate rule select the same three stocks in this sample.')
para('Table 2.3 Individual alphas exceeding the handout threshold',caption,4)
sig=capm.loc[capm.t_Alpha.abs()>2]
table(['Stock','Alpha % monthly','t alpha','p alpha','Direction'],[
    [r.Ticker,f'{100*r.Alpha_monthly:.3f}',f'{r.t_Alpha:.3f}',f'{r.p_Alpha:.4f}', 'Positive' if r.Alpha_monthly>0 else 'Negative'] for r in sig.itertuples()], [67,130,99,99,109])
para('MSFT and WMT earn positive sample returns unexplained by market exposure, while DIS has a negative deviation. Their p values are near 5%, so these are modest individual signals rather than overwhelming evidence. AAPL\'s alpha is positive at 0.838% per month, but its t statistic of 1.530 does not cross the threshold.')
para('Table 2.4 Observed versus chance significant counts',caption,4)
table(['Quantity','Number'],[['Stocks tested','29'],['Observed |t alpha| > 2','3'],['Approximate expected count if all alphas are zero','1.45']],[407,97])
h('What the count establishes')
para('If all true alphas are zero and each test operates at approximately the 5% level, the expected number of false positives is <b>29 x 0.05 = 1.45</b>. This expectation is a benchmark, not an upper limit. Observing three significant estimates is above the expected count, yet sampling variation can generate more than the expectation even when the joint null is true.')
para('The expectation adds the individual false-positive probabilities and does not require independence. However, independence would be needed for a simple binomial calculation of the count distribution. Stock regression errors can move together, so that distribution is not assumed here. We do not infer a formal joint p value from the difference between three and 1.45.')
para('Our assessment is therefore cautious: the three alphas flag possible pricing deviations for Stage 3, while the evidence supplied by this count is insufficient for a definitive joint rejection. Failure to reject individual alphas also does not prove they are zero. Conventional OLS inference relies on its error assumptions, and its reported p values may be sensitive to heteroskedasticity or serial correlation. No multiple-testing correction or formal joint test is used.')
c.showPage()

start(4)
h('2d The fitted SML versus theory')
para('In monthly percentage units, the empirical SML is <b>mean excess return = 0.610% + 0.571% x beta</b>. The sample CAPM benchmark is <b>mean excess return = 1.064% x beta</b>. A perfect match would require a zero intercept and a slope equal to the sample market premium. The fitted parameters differ in both directions.')
para('Table 2.5 SML parameter differences from theory',caption,4)
table(['Parameter','Fitted % monthly','Theory % monthly','Difference pp'],[
    ['Intercept','0.610','0.000','+0.610'],['Slope','0.571','1.064','-0.493']],[100,140,140,124])
h('A flatter slope')
para('The fitted slope is 53.7% of the theoretical slope, or 46.3% lower. A one-unit increase in estimated beta is associated with only 0.571 percentage points more monthly mean excess return across the stocks, compared with the 1.064 points implied by the sample market premium. Higher market exposure is associated with a smaller realized return increment than the CAPM benchmark predicts.')
para('The fitted lines cross at beta 1.237. Below that level the fitted empirical line lies above theory, and above it the fitted line lies below theory. At beta 0.5, the fitted mean is 0.896% versus 0.532% under theory; at beta 1.3, it is 1.353% versus 1.383%. These examples describe the fitted cross-sectional relationship, not every stock. An individual stock can fall on either side because of its own alpha.')
h('A positive intercept')
para('The fitted intercept is 0.610 percentage points per month above the theoretical zero. It summarizes the fitted excess return at beta zero, not the risk-free rate. Observed betas range from 0.277 to 1.389, so beta zero is outside the sample: the intercept is an extrapolation. We have not constructed a tradable zero-beta portfolio, and the positive intercept does not demonstrate a riskless profit opportunity.')
h('Interpretation and limits')
para('The sample pattern suggests that market beta alone does not fully organize realized average returns. Week 4 explains that a nonzero alpha can reflect mispricing, a missing risk factor or a poor market proxy. The positive fitted intercept and flatter slope are consistent with deviations worth investigating, but they do not identify which explanation is responsible.')
para('These parameter comparisons are descriptive. Betas are estimated regressors, realized mean returns are noisy, and the stocks share common shocks. The 2c chance-count assessment is not a formal test of the SML slope and intercept restrictions. We therefore avoid turning the fitted differences into a conclusive rejection of the population CAPM.')
para('The historical cohort retains later index removals, which mitigates current-member selection, but the old-DuPont exclusion leaves availability selection. A large-cap US equity proxy also differs from the unobservable portfolio of all wealth. Stage 3 should examine whether additional factors absorb MSFT, WMT and DIS alphas; Stage 4 should assess sensitivity to a different market proxy. Our Stage 2 finding is a flatter empirical SML and three marginal individual alpha signals, with a qualified verdict.')
para('Sources: FE5108 midterm project handout, Track A Stage 2; Week 4 CAPM slides 9 and 34-35; frozen Stage 1 data and methods. Risk-free and market series: Kenneth French Data Library, US monthly factors, 202608 vintage. Stock series: instructor bundle and cached Yahoo Finance data under the documented Stage 1 conventions.',small,0)
c.save()
print(OUT)
