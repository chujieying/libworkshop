# WVS Analysis — Agentic Workflow Workshop 2

Welcome! In this hands-on you'll **vibe-code a small data analysis**, put it under **version control**, and **publish it live on the web** — all in one sitting. You'll walk out with a real URL you can share.

> **Workshop:** Vibe-coding & Version Control in your Codex / Claude Code
> **Data:** A *synthetic* dataset modelled on the [World Values Survey](https://www.worldvaluessurvey.org/), covering five countries across Asia. This particular dataset is synthetic, so any results we get will be simulated. 

---

## Before we start

Open a terminal and run these. The first three must succeed, plus **at least one** of Python / R:

```bash
git --version        # any version is fine
gh auth status       # should say you're logged in to github.com
claude --version     # or: codex --version
python --version     # or: R --version  (either is fine — used to run the analysis)
```

If `gh auth status` says you're **not** logged in, run `gh auth login` and follow the prompts (choose **HTTPS** and authenticate in the browser). This is the one step that makes pushing to GitHub "just work" later. If anything here fails, come find Bella at the venue from **3:00 PM** for troubleshooting before the workshop starts.

---

## What's in this repo

| File | What it is |
|---|---|
| `data/wvs-synthetic.csv` | The dataset (synthetic, modelled on the WVS) |
| `PROMPT.md` | The prompt to paste into Claude Code / Codex |
| `.gitignore` | The "do not ship" list i.e. files Git will deliberately skip |
| `.nojekyll` | Tells GitHub Pages to serve our files as-is — **don't delete it** (see below) |
| `README.md` | This file |

We'll **generate/vibe-code** `index.html` during the workshop, which will get published.

> **What's `.nojekyll` and why keep it?** By default, GitHub Pages runs your files through a tool called Jekyll, which **ignores any folder whose name starts with `_`**. When R/Quarto renders your report, it puts all the plots, styles, and scripts in a folder like `index_files/` — so without this file, your page would load but the charts and styling would be missing. The empty `.nojekyll` file switches Jekyll off so everything publishes exactly as generated. It looks like junk, but leave it be.

---
