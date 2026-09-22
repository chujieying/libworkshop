# The prompt

Copy everything in the box below and paste it into **Claude Code** or **Codex**, running from inside this project folder.

---

Build a single, self-contained `index.html` that presents an exploratory analysis of a **simulated** World Values Survey–style dataset in `data/wvs-synthetic.csv`.

**Some context about the data**
- **This is synthetic (simulated) data.** The rows are fabricated to mirror the real World Values Survey (Wave 7) distributions and relationships, so no real respondent data is used. Treat any patterns as illustrative, not real-world results.
- Respondents are from 5 countries in different parts of Asia: Turkey (Middle East), India (South Asia), Singapore (Southeast Asia), China (East Asia), and Kazakhstan (Central Asia). Sample sizes vary by country (roughly 1,300–3,000 each).
- Some cells may be blank (missing).

**What to build**
1. Read and analyse `data/wvs-synthetic.csv`.
2. Produce a single `index.html` that is **fully self-contained** — with the data or the computed results embedded directly inside it — so it works both by double-clicking it locally and when served by GitHub Pages. It must **not** read the CSV at runtime.
3. In `index.html`:
   - Give the page a title and a short intro paragraph that: states clearly the data is **synthetic/simulated** i.e. fabricated to resemble the **World Values Survey, Wave 7** (include a citation and a link to worldvaluessurvey.org as the model it's based on). Notes that any findings are illustrative only, and lists the five countries.
   - present all the column names and their corresponding data types, with the non-empty number of observations for each.
   - do **not** put `respondent_id` in any chart or the list, it's just an identifier.
   - check for duplicates and report the result.
   - check for empty values. if found on any cell, remove that row from the analysis.
4. Produce the following analyses, each with the specified visualization and a 1–2 sentence plain-language takeaway beneath it. Round every number shown on screen (labels, axes, tooltips) to a sensible precision.
   - **Cultural map — emancipative vs secular values, all 5 countries.**  Plot each country's *average* on a scatter: x = `secular_values`, y = `emancipative_values`. One labelled point per country (5 points total, not individuals). This is the classic Inglehart–Welzel style map.
   - **Value fingerprints — radar chart, all 5 countries.**  One overlaid radar line per country across six measures, each normalised to 0–1: life satisfaction, share who trust others, importance of god, emancipative values, secular values, financial satisfaction. (Divide the 1–10 measures by 10; `trust_people` = share Trusted; the two indices are already 0–1.) Give each country a distinct colour **and** a distinct point marker.
   - **Individual values, China vs India — scatter.** Scatter of individual respondents on x = `secular_values`, y = `emancipative_values`, for China and India only. To keep it readable, randomly sample about 300 respondents per country rather than plotting all of them (seed this sample — see step 6 — so it is reproducible). Use a distinct colour **and** marker for each country, and mark each country's average as a larger outlined point. The takeaway should note how much the two clouds overlap despite different averages.
   - **Life vs financial satisfaction, Singapore — heatmap.** A 10×10 heatmap for Singapore only: rows = `life_satisfaction` (1–10), columns = `financial_satisfaction` (1–10), each cell shaded by the number of respondents in it (a single-hue light-to-dark scale). Build this with plain HTML/CSS/JS — it needs no charting library.
5. Keep each country's colour consistent across every chart, using this colour-blind-safe palette: China `#E69F00` (gold), Singapore `#D55E00` (red), Turkey `#CC79A7` (purple), India `#0072B2` (blue), Kazakhstan `#009E73` (teal). Wherever charts tell series apart by colour, also pair the colour with a distinct marker or line style.
6. Use whatever language is available on this machine — Python or R (prefer the standard library / minimal packages) — otherwise JavaScript. For reproducibility, also produce the script (Python, R, or JavaScript) that generates `index.html`, and set a fixed random seed so the script reproduces the same `index.html` every run.
7. Make it clean and responsive so it reads well on a laptop or phone.

When you're done, tell me how to **preview it locally**, then stop. I'll handle committing to Git and publishing myself.

---
