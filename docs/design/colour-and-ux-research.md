# Colour, vision and dashboard UX - research basis for the vn-market-elt palette

Date: 2026-10-13. Scope: Power BI Desktop dashboards, light and dark themes, Vietnamese equities.
Evidence marks: ✅ primary source read in this session · ⚠️ secondary source, or primary source known but not readable in this session (several w3.org / powerbi.microsoft.com / bloomberg.com pages returned HTTP 403 to the fetcher) · ❓ rule of thumb or unverified.
This file does not pick hex values. It gives the rules and starting coordinates that a measuring tool should test. The measured result is `config/palette.yml` (ADR-0026), checked by `tools/check_palette.py`.

---

## 1. Colour science basics

1.1 **Perceptual uniformity is the point of a colour space for design.** sRGB/HSL steps are not equal perceived steps; a palette built in HSL has uneven lightness across hues (HSL "50% lightness" yellow is far lighter than HSL 50% blue). MDN: the `L` in `oklch()` "specifies the color's perceived lightness", unlike the `L` in `hsl()`. ✅ [MDN oklch()](https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/oklch)

1.2 **CIELAB / CIELCh (1976)** is the classic perceptual space and still the input to CIEDE2000. Its known weakness: hue prediction, "in particular blue hues are predicted badly" - blues drift toward purple when chroma or lightness changes. ✅ [Ottosson, A perceptual color space for image processing (2020)](https://bottosson.github.io/posts/oklab/)

1.3 **OKLab / OKLCH (Ottosson 2020)** was fit to CAM16-derived equal-lightness and equal-chroma pairs plus IPT hue-uniformity data, optimising a CIEDE2000-based error. It keeps CAM16-like lightness/chroma prediction with simple, numerically stable maths, and fixes the blue hue shift. Caveat stated by the author: the lightness/chroma training data came from CAM16 itself, so it is not an independent validation against observers. ✅ [Ottosson](https://bottosson.github.io/posts/oklab/)

1.4 **Why OKLCH is now preferred for palette building:** it is in CSS Color Level 4 (`oklch()`), has polar L/C/H axes that map onto design decisions (lightness ramp, saturation cap, hue), and holding L constant while rotating H gives visually equal-lightness hues - which is exactly what a categorical palette or a light/dark token pair needs. ⚠️ [CSS Color 4 (W3C)](https://www.w3.org/TR/css-color-4/) (403 to fetcher) · ✅ [MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/oklch)
   - Practical caveat ❓: OKLCH can express colours outside sRGB; every token must be gamut-mapped to sRGB hex before it goes into a Power BI theme (Power BI takes `#RRGGBB` only ✅ [Microsoft Learn: custom themes](https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom)).

1.5 **Colour difference: CIEDE2000 (dE00)** is the current CIE formula; reference implementation notes and test data: Sharma, Wu & Dalal, Color Res. Appl. 30(1):21-30, 2005. Any tool used here should be validated against their test-pair file. ⚠️ [Sharma CIEDE2000 page](https://www.ece.rochester.edu/~gsharma/ciede2000/)

1.6 **What dE values mean in practice** (rules of thumb, not CIE thresholds):
   - CIE76 (dE*ab) JND ~2.3 (colour-science library constant `JND_CIE1976`). ⚠️ [colour docs](https://colour.readthedocs.io/en/latest/generated/colour.difference.JND_CIE1976.html)
   - dE00 ~1 is roughly one JND for large patches side by side; 1-2 visible only on close inspection. ❓ (vendor guidance, not CIE)
   - These thresholds are for **large uniform patches**. Szafir (IEEE TVCG 2018) measured that perceived differences shrink for small marks (points, thin lines, bars), so CIELAB-based metrics **underestimate** the difference needed in charts; thin lines need much larger dE than bars. ⚠️ [Szafir, Modeling Color Difference for Visualization Design](https://cmci.colorado.edu/visualab/VisColors/)
   - Commonly used dataviz targets: dE00 >= ~10 between categorical neighbours, and a CVD-simulated dE00 floor in the 6-10 band. ❓ The v1 project already measured with "CVD dE >= 8 target, 6-8 floor only with secondary encoding"; keep that convention unless new evidence overturns it.

1.7 **Lightness is the most robust channel.** It survives all three dichromacies, greyscale printing, projector wash-out and dark/light inversion. Crameri et al.: maps with an even, monotonic lightness gradient stay readable in black and white. Okabe & Ito: colour-blind viewers are often more sensitive to brightness and saturation differences, so "if two colours are both warm or both cool, make their brightness or saturation clearly different". ✅ [Crameri, Shephard & Heron, Nat. Commun. 11:5444 (2020)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7595127) · ✅ [Okabe & Ito, Color Universal Design](https://jfly.uni-koeln.de/color/)

---

## 2. Human vision and colour-vision deficiency (CVD)

2.1 **Prevalence.** ~8% of men and ~0.5% of women (Northern-European ancestry) have red-green CVD; lower elsewhere. ✅ [Crameri 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7595127). By ancestry: ~8% Caucasian, **~5% Asian**, ~4% African males. ✅ [Okabe & Ito](https://jfly.uni-koeln.de/color/). For a Vietnamese audience, plan for ~1 in 20 men.
   Split by type (men / women): deuteranomaly 4.63% / 0.36% · protanomaly 1.08% / 0.03% · deuteranopia 1.27% / 0.01% · protanopia 1.01% / 0.02% · tritanopia ~0.0001% · tritanomaly ~0.0002%. ⚠️ [Colblindor](https://www.color-blindness.com/types-of-color-blindness/) (no study named; consistent with Birch, JOSA A 29(3):313-320, 2012 ⚠️ [doi](https://doi.org/10.1364/JOSAA.29.000313)).
   => Deutan (green-weak) dominates; anomalous (partial) trichromats outnumber dichromats ~3:1, so severity matters, but designing for severity 1.0 covers everyone.

2.2 **Why red-green is the problem pair.** Protan and deutan defects affect L/M cones, collapsing the red-green opponent axis; colours that differ only along it (e.g. a green and a red of similar lightness) become near-identical yellow-brown/olive. The blue-yellow axis is preserved. Crameri: avoid red-green pairings of similar lightness. ✅ [Crameri 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7595127) · ✅ [Okabe & Ito](https://jfly.uni-koeln.de/color/)

2.3 **Simulation models.**
   - Brettel, Viénot & Mollon 1997 (dichromats, two half-planes) and Viénot, Brettel & Mollon 1999 (single-plane simplification for sRGB). ⚠️ (known citations, not fetched)
   - **Machado, Oliveira & Fernandes 2009**, IEEE TVCG 15(6):1291-1298, doi 10.1109/TVCG.2009.113: physiologically based, handles anomalous trichromacy **and** dichromacy in one model; the authors publish 3x3 matrices for protanomaly, deuteranomaly and tritanomaly at severity 0.0-1.0 in 0.1 steps (1.0 = dichromacy). This is the de-facto standard in tooling (R `colorspace`, Python `colour.matrix_cvd_Machado2009`, browser devtools). ✅ [Machado CVD simulation page, Table 1](https://www.inf.ufrgs.br/~oliveira/pubs_files/CVD_Simulation/CVD_Simulation.html) · ⚠️ [colour-science implementation](https://colour.readthedocs.io/en/latest/_modules/colour/blindness/machado2009.html)
   - Implementation pitfall ❓: the matrices are applied in **linear** RGB in standard implementations (decode sRGB gamma first, re-encode after). The authors' page does not state this explicitly; check against `colour` or `colorspace` output.
   - Machado's tritan matrices are less validated than protan/deutan (the paper's experiments covered protan/deutan). ⚠️

2.4 **Practical rules.** Vary lightness, not only hue; prefer vermilion over pure red (still readable to protanopes) and bluish green over pure green; label directly; add shape/line-style/hatching redundancy; thicker lines and larger symbols. ✅ [Okabe & Ito](https://jfly.uni-koeln.de/color/). Power BI's own docs: "Avoid using color as the only means of conveying information. Use text or icons." ✅ [Microsoft Learn: accessible reports](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports)

2.5 **Finance up/down specifically - how platforms handle it.**
   - **Futubull / moomoo** (red-up market): added a switchable **pink-green** scheme tested against protanopia and deuteranopia, **hollow (up) vs solid (down) candles** so direction does not rely on colour, and uses **blue/orange** "as much as possible" on main pages. ✅ [Android Developers case study: Futu](https://developer.android.com/stories/apps/futu)
   - **Bloomberg Terminal**: alternate colour schemes "optimized for the two main types of CVD" via `PDFU COLORS <GO>`; Bloomberg estimates ~20,000 users with CVD. ⚠️ [Bloomberg UX accessibility](https://www.bloomberg.com/ux/accessibility/) (403 to fetcher; seen in search snippet) · ⚠️ [Tech at Bloomberg](https://www.techatbloomberg.com/blog/designing-the-terminal-for-color-accessibility/)
   - **FxPro** app: "Colour Adjust" with pairs Red/Blue, Red/Green, Orange/Green, Yellow/Blue, Monochrome, applied app-wide. ⚠️ [BrokerXplorer](https://www.brokerxplorer.com/news/fxpro-adds-colour-adjust-feature-to-awardwinning-trading-app-7824)
   - **Robinhood**: an "Accessible Colors" toggle for red-green CVD is reported, but the help page read here only points to OS colour filters. ❓ [Robinhood accessibility](https://robinhood.com/gb/en/support/articles/accessibility-options/)
   - **TradingView**: no documented colour-blind mode found; up/down body/border/wick colours are user-editable per chart. ❓
   - Pattern across platforms: **keep the cultural default, add (a) a non-colour cue and (b) an opt-in CVD scheme.** The CVD alternatives cluster on blue/orange (Okabe-Ito blue #0072B2 / orange #E69F00 or vermilion #D55E00) and pink/green.
   - Okabe-Ito hexes as reproduced from Wong, Nat. Methods 8:441 (2011): black #000000, orange #E69F00, sky blue #56B4E9, bluish green #009E73, yellow #F0E442, blue #0072B2, vermilion #D55E00, reddish purple #CC79A7. ⚠️ [Wong 2011 PDF mirror](https://nature.berkeley.edu/garbelottoat/wp-content/uploads/nmeth.1618.pdf-WT.pdf) · Krzywinski notes source-table vs swatch mismatches. ⚠️ [mk.bcgsc.ca](https://mk.bcgsc.ca/colorblind/palettes.mhtml)

---

## 3. Contrast and accessibility standards

3.1 **WCAG 2.2** (current W3C Recommendation; criteria unchanged from 2.1 for these items). ⚠️ [WCAG 2.2](https://www.w3.org/TR/WCAG22/) (403 to fetcher; text is well known)
   - **1.4.3 Contrast (Minimum), AA:** text >= **4.5:1**; large text (>= 18pt, or >= 14pt bold) >= **3:1**.
   - **1.4.6 Contrast (Enhanced), AAA:** 7:1 / 4.5:1.
   - **1.4.11 Non-text Contrast, AA:** graphical objects "required to understand the content" (chart marks, focus rings, UI boundaries) >= **3:1 against adjacent colours**.
   - **1.4.1 Use of Color, A:** colour must not be the only visual means of conveying information.
   - Power BI applies the same: title/axis/data-label text >= 4.5:1, and its Accessible themes target 3:1 for graphical parts, with line charts as a known exception requiring manual review. ✅ [Learn: accessible reports](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports) · ⚠️ [Power BI blog: accessible colour themes](https://powerbi.microsoft.com/blog/create-stunning-and-more-accessible-reports-in-minutes-with-our-new-color-themes)

3.2 **APCA / WCAG 3.** APCA was removed from the WCAG 3 working draft in 2023; the March 2026 draft says the contrast algorithm "is yet to be determined"; no Recommendation date. Use APCA (Lc values) as a **supplementary** check only - WCAG 2.2 ratios remain the citable requirement. ⚠️ [Roselli, WCAG3 contrast as of April 2026](https://adrianroselli.com/2026/04/wcag3-contrast-as-of-april-2026.html) · ⚠️ [W3C WCAG 3 explainer](https://www.w3.org/TR/wcag-3.0-explainer)
   - Why it still matters here ❓: the WCAG 2 luminance ratio is known to overrate light-on-dark pairs, so dark-mode text that barely passes 4.5:1 can read worse than its light twin. A second APCA check on dark tokens is cheap.

---

## 4. Dataviz palette design

4.1 **Categorical palettes - keep them short.** Tableau 10: a full hue circle with simple colour names (red, blue, purple, brown) because they are visually distinct and nameable; Tableau 20 = light/dark pairs; the 2016 redesign lowered chroma ("more subdued") and tuned by hand. ✅ [Tableau: How we designed the new color palettes in Tableau 10](https://www.tableau.com/about/blog/2016/7/colors-upgrade-tableau-10-56782). ColorBrewer qualitative sets top out at 8-12 and are rated for CVD/print safety. ⚠️ [ColorBrewer](https://colorbrewer2.org/) · Harrower & Brewer, Cartographic J. 40(1), 2003 ⚠️. Practical ceiling 5-8 categories; beyond that, group into "other" or use small multiples. ❓
4.2 **IBM Carbon dataviz palette:** 14 categorical colours applied **in a fixed order** chosen to maximise contrast between neighbours; separate light and dark values; single-hue 10-step sequentials; in light themes the darkest step = largest value, in dark themes the **lightest** = largest; two diverging palettes (red-cyan for hot/cold, purple-teal for "performance or sales"); a separate 4-colour **status** palette (red/orange/yellow/green) kept apart from data colours. ✅ [Carbon: data-viz colour palettes](https://carbondesignsystem.com/data-visualization/color-palettes/)
4.3 **Sequential:** one hue (or a short hue path) with monotonic lightness. **Diverging:** two sequentials meeting at a **neutral, low-chroma midpoint**; both arms symmetric in lightness. Crameri: use diverging maps for data centred on a meaningful value; never rainbow/jet (non-uniform, yellow band reads as a feature, >7% visual error of the data range); treat any non-"scientifically derived" map with suspicion; always show the colour bar. ✅ [Crameri 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7595127). Viridis (matplotlib default since 2.0) and cividis (CVD-optimised, linear brightness, near-identical reading for CVD and normal viewers) are safe sequential defaults. ⚠️ [matplotlib colormaps](https://matplotlib.org/stable/users/explain/colors/colormaps.html) · ⚠️ [Nunez et al., PLOS ONE 13(7):e0199239 (2018)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6070163)
   - "Why not yellow in the middle": a yellow midpoint is the brightest point of the scale and reads as an extreme, not as zero. This matches the v1 rule "midpoint of a polar scale must be neutral". ✅ (Crameri, rainbow/yellow argument)
4.4 **Semantic colour: reserve colour for meaning.** Things that mean the same look the same; things that differ look different (IBCS semantic notation: solid = actual, outline = plan, hatched = forecast; green = positive variance, red = negative, with explicit "+"/"-" signs). ⚠️ [IBCS semantic notation](https://www.ibcs.com/resource/semantic-notation-ibcs-public-seminar-sap) · IBCS was reported as ratified ISO 24896 ⚠️ unverified. No IBCS-specific CVD rule found. ❓
   - Consequence: the up/down/ceiling/floor/reference hues must **not** also appear in the categorical `dataColors` sequence, or a "blue sector" will be read as "floor".
4.5 **Tufte / Few:** maximise data-ink, remove chartjunk; Few: muted base colours, one saturated colour for emphasis, avoid gauges/3D. ⚠️ (Tufte 1983 *Visual Display of Quantitative Information*; Few 2006 *Information Dashboard Design*, books not read here)

---

## 5. Dark mode

5.1 Material (M2): recommended dark surface **#121212**, not pure black, because elevation (shadows/lighter surfaces) is easier to express on dark grey; dark surface with 100% white body text gives >= **15.8:1**. ⚠️ [Material 2 dark theme](https://m2.material.io/design/color/dark-theme) (content from search snippet; page did not render to fetcher)
5.2 Material codelab: **lighter variants** of brand colours are used on dark surfaces because "saturated colors vibrate" against dark backgrounds and are harder to read; elevation via white overlays (2% cards ... 12% app bar in the example); text emphasis by opacity **87% high / 60% medium / 38% disabled** - pure #FFFFFF text can reduce legibility. ✅ [Google codelab: Design a dark theme](https://codelabs.developers.google.com/codelabs/design-material-darktheme)
5.3 Consequences for charts ❓: each semantic colour needs a **separate dark token** (raise L, cut C), not the light hex reused; sequential ramps invert direction (lightest = most, per Carbon ✅ 4.2); gridlines and borders must stay >= 3:1 only if they carry meaning (gridlines usually decorative and should be faint).
5.4 Power BI note: Microsoft ships **Dark** and **Soft dark** built-in themes but says "before you publish, select Reset to default" - Microsoft treats dark as an authoring convenience, so a published dark theme is our own responsibility, including setting `firstLevelElements`, `secondLevelElements` and `background` explicitly or labels become unreadable. ✅ [Learn: report themes](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-report-themes) · ✅ [Learn: custom themes](https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom)

---

## 6. Market colour conventions

6.1 **Vietnam (HOSE/HNX/UPCoM price boards): green = up, red = down**, plus **purple (tim) = ceiling**, **cyan/light blue (xanh lo) = floor**, **yellow (vang) = reference (unchanged)**. ✅ [DNSE (licensed broker) - colours on the price board](https://www.dnse.com.vn/hoc/cac-mau-trong-bang-gia-chung-khoan) · ⚠️ [Finhay](https://www.finhay.com.vn/cac-mau-trong-bang-chung-khoan) · ⚠️ [Vietcetera](https://vietcetera.com/vn/5-giay-doc-bang-dien-chung-khoan). No exchange (HOSE/HNX) rulebook text on colours was found - it is a market convention, not a regulation. ❓
6.2 **East Asia reverses up/down:** China (red = wealth, green = illness), with Japan and Korea described the same by the EU data-visualisation guide; Taiwan likewise. ⚠️ [data.europa.eu: colour connotations](https://data.europa.eu/apps/data-visualisation-guide/colour-connotations) · ⚠️ [Futu case study](https://developer.android.com/stories/apps/futu) · Japan/Korea practice was historically mixed (black-up, blue-down seen). ⚠️ [W3C i18n list 2005](https://lists.w3.org/Archives/Public/www-international/2005JulSep/0189.html)
6.3 => **VN follows the Western green-up convention.** Readers of this repo (Vietnamese traders, international reviewers) both expect green-up; there is no cultural reason to flip it.
6.4 Collision to watch: in VN, **cyan/blue already means "floor"** and purple "ceiling". A blue/orange CVD mode puts blue on "up", contradicting the board convention exactly where floor stocks are shown. Under deutan simulation purple and blue also converge. ❓ (inference; must be measured)

---

## 7. Power BI specifics

7.1 Theme JSON: only `name` is required. Colour keys: `dataColors` (any length; Power BI auto-generates more by shifting saturation/hue when exhausted), `good`/`neutral`/`bad` (**used only by the waterfall chart and KPI visual**, plus named colours in DAX), `maximum`/`center`/`minimum`/`null` (conditional-formatting gradients), structural `firstLevelElements` (= foreground), `secondLevelElements`, `thirdLevelElements` (gridlines), `fourthLevelElements`, `background`, `secondaryBackground`, `tableAccent`, `hyperlink`, etc.; `textClasses` (callout/title/header/label primaries; secondaries inherit). JSON schema published in `microsoft/powerbi-desktop-samples`. ✅ [Learn: custom themes](https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom)
7.2 **Named theme colours in DAX**: a Field-value conditional-format measure can return `"good"`, `"bad"`, `"neutral"`, `"foreground"`, `"minColor"`/`"midColor"`/`"maxColor"` etc. instead of hex, so swapping the theme file swaps the colours. Conditional-formatting rules themselves **cannot** live in a theme. ✅ [Learn: custom themes](https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom)
7.3 Accessibility guidance for reports: text >= 4.5:1 (WCAG 2.1 1.4.3 cited); don't use colour alone; turn on **markers with different shapes per series** for line/area/combo/scatter; test with Coblis/Vischeck; listed hard pairs to avoid on one page: green/red, green/brown, blue/purple, green/blue, light green/yellow, blue/grey, green/grey, green/black; keep pages simple, same fonts/sizes, slicers in the same place on every page; don't put essential information in tooltips; squint test. ✅ [Learn: accessible reports](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports)
7.4 **High contrast:** Desktop detects Windows high-contrast themes and applies them; the colours follow the published report; in embedding, high-contrast mode overrides any theme (cannot apply both). ✅ [Learn: accessible reports](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports) · ⚠️ [Embedded accessibility docs](https://learn.microsoft.com/en-us/javascript/api/overview/powerbi/accessibility)
7.5 Built-in themes now: Bloom, Dark, Divergent, Frontier, Innovate, Soft dark, Tidal, Copilot default; Learn also links a community **"Color-blind friendly" (ColorblindSafe-Longer.json)** theme. ✅ [Learn: report themes](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-report-themes). An "Accessible ..." theme family was announced on the Power BI blog. ⚠️ (403 to fetcher)
7.6 Implementation of a runtime CVD mode in Power BI ❓: there is no viewer-side theme switch in the service. Options: (a) ship two theme JSONs (author choice, not viewer choice); (b) a disconnected "palette" slicer table + DAX colour measures returning hex per mode (viewer choice, but every conditional format must route through the measure, and theme-level `good/bad` will not follow); (c) bookmarks. (b) is the only viewer-facing toggle.

---

## 8. UX/UI for analytical dashboards (evidence-backed essentials)

8.1 **Encoding accuracy ranking** (Cleveland & McGill, JASA 79(387):531-554, 1984): position on a common scale > position on non-aligned scales > length > angle/direction > area > volume/curvature > shading/colour saturation; replicated on Mechanical Turk by Heer & Bostock (CHI 2010). => bars/dots/lines for quantities; **no pie, donut, gauge or 3D** for comparison; colour is for categories and flags, not for reading magnitudes. ⚠️ [JSTOR 2288400](https://www.jstor.org/stable/2288400) · ⚠️ [Cornell course summary](https://info3312.infosci.cornell.edu/slides/04-graphical-perception.html)
8.2 **Reading order:** without strong cues users scan in an F-pattern (first lines fully, then the left edge); headings, bold key terms and grouping change the pattern. => KPIs/answer top-left, labels left-aligned, the first words of a title carry the meaning. ✅ [NN/g: F-shaped pattern](https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content/)
8.3 **One question per visual; few visuals per page;** split overloaded visuals; consistent fonts and positions across pages. ✅ [Learn: accessible reports](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports)
8.4 **Pre-attentive attributes** (hue, intensity, size, orientation, enclosure) pop out in < ~250 ms - but only if used sparingly; one highlight colour against a muted base. ⚠️ (Healey & Enns, IEEE TVCG 18(7), 2012; Few 2006)
8.5 **Data-ink:** light or no gridlines, no borders/shadows on visuals, direct labels instead of legends where possible (Okabe & Ito ✅ recommends direct labelling too).
8.6 **Small multiples and sparklines** for many series instead of one chart with 10 colours (Tufte). ⚠️
8.7 **Number formatting** ❓: right-aligned, fixed decimals per column, thousands separators, units in the title not in every cell, signed changes ("+1.2%"), and the same format everywhere a measure appears. IBCS treats the explicit "+" as semantic. ⚠️
8.8 **Progressive disclosure / Nielsen heuristics** most relevant: visibility of system status (as-of date, data freshness), consistency and standards (same colour = same meaning), recognition rather than recall (labels on charts), aesthetic and minimalist design. ⚠️ [NN/g 10 heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/). Key info must not sit only behind interaction or tooltips. ✅ (Learn checklist)

---

## 9. Implications for this project

### 9.1 Testable rules (the measuring tool should check each one, per theme)

| # | Rule | Threshold (start value, calibrate by measuring) | Source |
|---|---|---|---|
| R1 | Body text vs its background | >= 4.5:1 (WCAG 2.2 1.4.3), both themes | §3.1 |
| R2 | Large text (>= 18pt / 14pt bold), KPI callouts | >= 3:1; aim 4.5:1 anyway | §3.1 |
| R3 | Every meaning-carrying mark (bars, lines, candles, up/down cells) vs background | >= 3:1 (1.4.11) | §3.1 |
| R4 | Up vs down pair, normal vision | dE00 >= 20 ❓ and OKLCH dL >= 0.10 ❓ | §1.6-1.7 |
| R5 | Up vs down pair, Machado 2009 severity 1.0, protan **and** deutan | dE00 >= 8 target; 6-8 allowed only with R7 cues present; < 6 fail | §2.3, v1 convention |
| R6 | Same pair, tritan severity 1.0 | dE00 >= 8 (cheap; tritan is rare but blue/teal options live on its axis) | §2.3 |
| R7 | Up/down never by colour alone | sign (+/-), arrow glyph, or hollow-vs-solid candle present on every up/down encoding | §2.4-2.5, WCAG 1.4.1 |
| R8 | The five price-board states (up, down, ceiling, floor, reference) | pairwise CVD-simulated dE00 >= 6; ceiling/floor also distinguished by glyph or label | §6.1, §6.4 |
| R9 | Categorical `dataColors` | <= 8 used; adjacent pairs dE00 >= 10 normal, >= 6 under protan/deutan; none closer than dE00 10 to a semantic colour | §4.1, §4.4 |
| R10 | Sequential ramps | OKLCH L strictly monotonic, roughly equal dL steps; lightest = most in dark theme | §4.2-4.3 |
| R11 | Diverging ramps | midpoint chroma ~0 (OKLCH C < 0.02), arms symmetric in L within 0.03; no yellow midpoint | §4.3 |
| R12 | Dark background | not #000; OKLCH L ~0.17-0.22 (#121212 is L ~0.18); high-emphasis text not pure white | §5.1-5.2 |
| R13 | Dark-theme semantic tokens | separate tokens; chroma at or below the light token, L raised until R3 passes | §5.2-5.3 |
| R14 | Greyscale test | every legend distinguishable on L alone (dL >= 0.08 between any two co-occurring series) ❓ | §1.7 |
| R15 | Power BI wiring | `good`/`bad`/`neutral` = up/down/reference; DAX formats return named colours, not hex; markers with distinct shapes on multi-line charts; check under Windows high contrast | §7 |

Rules R4/R6/R14 thresholds are ❓ starting points; R1-R3 are normative; R5 matches the threshold the v1 project already measured with.

### 9.2 Candidate directions for the up/down pair (OKLCH starting points, not final)

**A. VN-native, lightness-split (recommended default).** Keep green-up / red-down, but pull green toward **bluish green** and red toward **vermilion**, and separate them in lightness so the pair survives deutan as "light vs dark". Start: up `oklch(0.68 0.15 160)`, down `oklch(0.56 0.19 30)`; dark theme: up `oklch(0.76 0.13 160)`, down `oklch(0.68 0.16 30)`. Plus mandatory R7 cues.
- For: zero learning cost for VN readers; follows Okabe-Ito's own substitution (bluish green, vermilion); consistent with v1 findings that bold/deep red-green pairs can pass with secondary encoding.
- Against: under deutan the pair becomes two olive/brown tones distinguished mainly by L - fine for cells and bars, weaker for thin lines (Szafir); expect R5 near the 6-8 band on light background, better on dark (v1 measured the same asymmetry).

**B. Teal / vermilion (CVD-safer, still "green-ish up").** Rotate up further toward teal so it gains a blue component the deutan axis keeps. Start: up `oklch(0.66 0.12 185)`, down `oklch(0.60 0.19 38)`.
- For: larger simulated dE00 than A at the same lightness gap; still reads as "green-blue = good" to most viewers.
- Against: teal sits next to the VN **floor = cyan** convention (R8 risk); must keep floor distinctly bluer/lighter or mark floor with a glyph.

**C. Blue / orange as an opt-in colour-blind mode.** Up `oklch(0.58 0.14 250)` (Okabe-Ito blue region), down `oklch(0.74 0.15 65)` (Okabe-Ito orange region). Offered as a viewer toggle (§7.6 option b), never as the default.
- For: the pair used by Futu, FxPro and Okabe-Ito; separated on the blue-yellow axis that every common CVD keeps; strongest R5 margin.
- Against: breaks the VN convention (blue = floor on boards); every conditional format must route through a mode-aware DAX measure, and theme `good`/`bad` (waterfall, KPI) will not follow the toggle; doubles the test matrix (2 themes x 2 modes).

Suggested decision path ❓: measure A first against R1-R15 in both themes; if R5 lands below 8 on light background for line encodings, either thicken lines/add markers (cheap) or move to B; build C only if a reader asks for it, since the R7 cues already make A usable for CVD readers.
