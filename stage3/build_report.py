"""Build the four-page Stage 3 report from reproduced outputs."""
from pathlib import Path
import json
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pandas as pd
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.platypus import Image, Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas

BASE = Path(__file__).resolve().parent
OUT = BASE / "reports/Stage3_Factors_Report.pdf"
OUT.parent.mkdir(exist_ok=True)

font_candidates = [Path("/System/Library/Fonts/Supplemental"), Path("/usr/share/fonts/truetype/liberation2")]
for folder in font_candidates:
    regular = folder / "Arial.ttf" if (folder / "Arial.ttf").exists() else folder / "LiberationSans-Regular.ttf"
    bold = folder / "Arial Bold.ttf" if (folder / "Arial Bold.ttf").exists() else folder / "LiberationSans-Bold.ttf"
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont("Body", str(regular)))
        pdfmetrics.registerFont(TTFont("BodyBold", str(bold)))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="BodyBold", italic="Body", boldItalic="BodyBold")
        break
FONT = "Body" if "Body" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
BOLD = "BodyBold" if FONT == "Body" else "Helvetica-Bold"

body = ParagraphStyle("Body", fontName=FONT, fontSize=10, leading=13.3, spaceAfter=8)
small = ParagraphStyle("Small", parent=body, fontSize=8.1, leading=10.2)
heading = ParagraphStyle("Heading", parent=body, fontName=BOLD, fontSize=13, leading=16)
caption = ParagraphStyle("Caption", parent=body, fontName=BOLD, fontSize=9, leading=11.4)

cmp = pd.read_csv(BASE / "results/alpha_comparison.csv")
fac = pd.read_csv(BASE / "results/factor_summary.csv")
joint = pd.read_csv(BASE / "results/joint_alpha_tests.csv")
summary = json.loads((BASE / "results/stage3_summary.json").read_text())

c = canvas.Canvas(str(OUT), pagesize=(612, 792))
c.setTitle("Stage 3 Factors")
c.setAuthor("FE5108 Group Project")
LEFT, WIDTH, y = 54, 504, 730


def start(page, title=None):
    global y
    c.setFont(FONT, 8)
    c.drawString(54, 764, "FE5108  |  Group project  |  Stage 3")
    c.drawRightString(558, 28, f"Stage 3  |  {page}")
    y = 730
    if title:
        c.setFont(BOLD, 18)
        c.drawString(LEFT, y, title)
        y -= 29


def para(text, style=body, gap=8):
    global y
    p = Paragraph(text, style)
    _, height = p.wrap(WIDTH, 700)
    assert y - height >= 48, f"Page overflow near {text[:70]!r}; y={y}, h={height}"
    p.drawOn(c, LEFT, y - height)
    y -= height + gap


def h(text):
    para(text, heading, 7)


def table(headers, rows, widths=None, fontsize=8.7, highlight_rows=None):
    global y
    data = [headers] + rows
    t = Table(data, colWidths=widths or [WIDTH / len(headers)] * len(headers))
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTNAME", (0, 0), (-1, 0), BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), fontsize), ("LEADING", (0, 0), (-1, -1), fontsize + 2),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#E6EBEF")),
        ("GRID", (0, 0), (-1, -1), 0.3, HexColor("#D2D2D2")),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for row_index in highlight_rows or []:
        commands.append(("BACKGROUND", (0, row_index + 1), (-1, row_index + 1), HexColor("#FFF1D6")))
    t.setStyle(TableStyle(commands))
    _, height = t.wrap(WIDTH, 700)
    assert y - height >= 48, f"Table overflow; y={y}, h={height}"
    t.drawOn(c, LEFT, y - height)
    y -= height + 9


start(1, "Stage 3 Factors")
h("Introduction")
para("Stage 2 found a flatter empirical Security Market Line and three marginal CAPM alpha signals: positive estimates for MSFT and WMT and a negative estimate for DIS. Stage 3 asks whether those returns are compensation for systematic size and value exposures rather than CAPM pricing errors. We therefore add the two factors already frozen in the Kenneth French data: SMB and HML.")
para("The controlled comparison retains the same 29 historical Dow Jones stocks, the same 130 monthly observations from November 2015 through August 2026, and the same stock-return, corporate-action and risk-free-rate conventions. Only the regression specification changes. For stock i, the Fama-French three-factor model is:", gap=4)
# Render mathematical notation with serif math glyphs and true subscripts.
equation = (r"$R_{i,t}-R_{f,t}=\alpha_i+\beta_{i,M}(R_{M,t}-R_{f,t})"
            r"+\beta_{i,\mathrm{SMB}}\,\mathrm{SMB}_t"
            r"+\beta_{i,\mathrm{HML}}\,\mathrm{HML}_t+\varepsilon_{i,t}$")
with plt.rc_context({"mathtext.fontset": "stix", "font.family": "serif"}):
    fig = plt.figure(figsize=(10, 0.55))
    fig.text(0.5, 0.5, equation, ha="center", va="center", fontsize=19)
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=400, bbox_inches="tight", pad_inches=0.05, transparent=True)
    plt.close(fig)
buffer.seek(0)
equation_image = Image(buffer)
equation_height = WIDTH * equation_image.imageHeight / equation_image.imageWidth
equation_image.drawWidth = WIDTH
equation_image.drawHeight = equation_height
equation_image.drawOn(c, LEFT, y - equation_height)
y -= equation_height + 12
para("All inputs are monthly decimals. RF is subtracted once from each stock return; Mkt-RF, SMB and HML are already factor returns. Conventional OLS standard errors match Stage 2, so before-versus-after differences are not caused by a new inference method.")
h("3a Factor construction")
para("<b>SMB - Small Minus Big.</b> Kenneth French forms six value-weighted portfolios from independent size and book-to-market sorts. SMB is the average return on the three small-stock portfolios minus the average return on the three big-stock portfolios. A positive loading means the stock co-moves more with the small-cap side; a negative loading indicates large-cap behavior. SMB is a tradable long-short factor return, not a firm characteristic inserted directly into the regression.")
para("<b>HML - High Minus Low.</b> HML is the average return on the high book-to-market portfolios minus the average return on the low book-to-market portfolios, combining the small- and big-stock legs. High book-to-market firms are conventionally called value stocks and low book-to-market firms growth stocks. A positive loading indicates value-like co-movement; a negative loading indicates growth-like co-movement.")
para("Table 3.1 Factor behavior over the common sample", caption, 4)
table(["Factor", "Mean % monthly", "Vol. % monthly", "Mean % annual", "Vol. % annual"], [
    [r.Factor, f"{100*r.Mean_monthly:.3f}", f"{100*r.Std_monthly:.3f}",
     f"{100*r.Annualized_arithmetic_mean:.3f}", f"{100*r.Annualized_volatility:.3f}"] for r in fac.itertuples()
], [70, 108, 108, 108, 110], 8.5)
para("The sample factor means are realized historical premia, not precisely known population rewards. SMB averages -0.129% per month and HML approximately zero, underscoring the course warning that factor premia are noisy over a single decade.", small, 0)
c.showPage()

start(2)
h("3b Alphas before and after adding factors")
para("Alpha is model-relative. Under the CAPM, returns associated with size or value exposure appear in alpha; under FF3, the corresponding factor loadings move those returns into required return. Figure 3.1 pairs each stock's Stage 2 CAPM alpha with its FF3 alpha. Red outlines identify the three Stage 2 signals.", gap=7)
im = Image(str(BASE / "figures/alpha_before_after.png"), width=475, height=431.8)
im.drawOn(c, LEFT + 14.5, y - 431.8)
y -= 440
para("Figure 3.1 Adding SMB and HML reduces several alpha magnitudes, but many paired estimates move only modestly; the Stage 2 signals remain economically visible even though none retains |t(alpha)| above 2.", caption, 9)
para("Table 3.2 Model-level comparison", caption, 4)
table(["Quantity", "CAPM", "FF3", "Change"], [
    ["Stocks with |t(alpha)| > 2", "3", "0", "-3"],
    ["Median |alpha|, % monthly", f"{100*summary['median_abs_alpha_capm']:.3f}", f"{100*summary['median_abs_alpha_ff3']:.3f}", f"{100*(summary['median_abs_alpha_ff3']-summary['median_abs_alpha_capm']):+.3f}"],
    ["Mean time-series R squared", f"{summary['mean_R_squared_capm']:.3f}", f"{summary['mean_R_squared_ff3']:.3f}", f"{summary['mean_R_squared_ff3']-summary['mean_R_squared_capm']:+.3f}"],
], [245, 82, 82, 95])
para("Median absolute alpha falls from 0.386% to 0.311% per month, while mean time-series R squared rises from 0.279 to 0.360. The higher R squared is expected when regressors are added and describes return variation, not pricing success by itself.", small, 0)
c.showPage()

start(3)
h("3b Stock-level alpha comparison")
para("Table 3.3 reports every stock's monthly alpha and conventional t statistic under both models. The comparison preserves estimates that do not cross a significance threshold: economic magnitude and sampling uncertainty should be read together.")
para("Table 3.3 CAPM and FF3 monthly alpha estimates", caption, 4)
rows = []
for r in cmp.itertuples():
    rows.append([r.Ticker, f"{100*r.CAPM_Alpha_monthly:.3f}", f"{r.CAPM_t_Alpha:.3f}",
                 f"{100*r.FF3_Alpha_monthly:.3f}", f"{r.FF3_t_Alpha:.3f}", f"{r.FF3_R_squared:.3f}"])
table(["Stock", "CAPM alpha %", "CAPM t", "FF3 alpha %", "FF3 t", "FF3 R sq."], rows,
      [54, 97, 78, 97, 78, 100], 7.6,
      [i for i, r in enumerate(cmp.itertuples()) if r.Ticker in {"MSFT", "WMT", "DIS"}])
para("Amber rows are the Stage 2 signals. No FF3 alpha exceeds the handout's approximate |t| > 2 threshold. DIS is essentially at the boundary (t = -1.9999), so rounding it to -2.000 must not be used to claim a robust disappearance. NKE becomes the largest FF3 alpha in absolute magnitude (-1.174% monthly) but remains below the threshold (t = -1.875).", small, 0)
c.showPage()

start(4)
h("3c Which Stage 2 anomalies are absorbed?")
para("We call a signal fully absorbed only when its FF3 alpha loses statistical significance <i>and</i> its absolute magnitude falls by at least half. If significance disappears but more than half of the CAPM alpha remains, we call it partially absorbed. This rule prevents a mechanical threshold crossing from being presented as a complete economic explanation.")
focus = cmp.set_index("Ticker").loc[["MSFT", "WMT", "DIS"]].reset_index()
para("Table 3.4 Verdict on the Stage 2 signals", caption, 4)
table(["Stock", "CAPM alpha %", "FF3 alpha %", "FF3 t", "FF3 R sq.", "Verdict"], [
    [r.Ticker, f"{100*r.CAPM_Alpha_monthly:.3f}", f"{100*r.FF3_Alpha_monthly:.3f}",
     f"{r.FF3_t_Alpha:.3f}", f"{r.FF3_R_squared:.3f}", r.Verdict] for r in focus.itertuples()
], [48, 91, 87, 65, 72, 141], 8.4, [0, 1, 2])
para("<b>MSFT - partially absorbed.</b> Alpha falls from 0.935% to 0.741% per month and t(alpha) from 2.015 to 1.864. Strong negative SMB (-0.615) and HML (-0.551) loadings identify large-growth behavior, while R squared rises from 0.389 to 0.566. The factors improve the return description, but 79% of the CAPM alpha magnitude remains.")
para("<b>WMT - partially absorbed.</b> Alpha falls from 0.952% to 0.801% and t(alpha) from 2.113 to 1.813. Its negative SMB loading (-0.459) is statistically material, but the HML loading is small. About 84% of the CAPM alpha remains, so size and value do not fully account for the return.")
para("<b>DIS - only marginally absorbed.</b> Alpha changes from -1.170% to -1.147%; t(alpha) moves from -2.068 to -1.9999 and R squared rises by only 0.002. SMB and HML loadings are small. The binary significance flag changes, but the economic estimate barely does; DIS is therefore the clearest surviving anomaly in substance.")
h("Joint evidence and verdict")
capm_grs = joint.loc[joint.Model == "CAPM"].iloc[0]
ff3_grs = joint.loc[joint.Model == "Fama-French 3-factor"].iloc[0]
para(f"As a robustness check, the GRS statistic falls from {capm_grs.GRS_statistic:.3f} (p = {capm_grs.p_value:.3f}) under CAPM to {ff3_grs.GRS_statistic:.3f} (p = {ff3_grs.p_value:.3f}) under FF3. Neither model is jointly rejected at 5% under the test's assumptions. This is consistent with Stage 2's cautious chance-count conclusion and does not prove all population alphas are zero.")
para("Our verdict is qualified: SMB and HML improve explanatory power and remove the three approximate individual significance flags, but they do not economically erase the Stage 2 signals. MSFT and WMT are partly related to large-growth exposure; DIS is scarcely explained. The analysis uses individual large-cap stocks rather than diversified sorted portfolios, so residual noise remains substantial and the APT's strongest diversified-portfolio implication is not directly tested.")
para("Sources: FE5108 midterm project handout, Track A Stage 3; FE5108 Weeks 5-6 course material, slides 48-55; Kenneth French Data Library US monthly research factors, 202608 vintage; frozen Stage 1-2 stock-return and cleaning conventions.", small, 0)
c.save()
print(OUT)
