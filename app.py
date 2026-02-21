import os
import time
import re
import json
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import streamlit as st

# ══════════════════════════════════════════════
#  CONFIGURAZIONE PAGINA
# ══════════════════════════════════════════════

st.set_page_config(
    page_title="Content Brief Generator",
    page_icon="📋",
    layout="centered",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap');

  html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
  }
  h1, h2, h3 {
    font-family: 'Syne', sans-serif !important;
  }

  /* Header hero */
  .hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 60%, #0ea5e9 100%);
    border-radius: 16px;
    padding: 2.5rem 2rem;
    margin-bottom: 2rem;
    text-align: center;
  }
  .hero h1 {
    color: #fff;
    font-size: 2.2rem;
    font-weight: 800;
    margin: 0 0 .5rem;
    letter-spacing: -.02em;
  }
  .hero p {
    color: rgba(255,255,255,.7);
    font-size: 1rem;
    margin: 0;
  }
  .badge {
    display: inline-block;
    background: rgba(14,165,233,.3);
    border: 1px solid rgba(14,165,233,.5);
    color: #7dd3fc;
    border-radius: 20px;
    padding: .2rem .85rem;
    font-size: .75rem;
    font-family: 'Syne', sans-serif;
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-bottom: 1rem;
  }

  /* Card sezioni */
  .section-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
  }

  /* Brief output */
  .brief-output {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 2rem;
    margin-top: 1.5rem;
    line-height: 1.8;
    font-size: .95rem;
  }

  /* Sticker step */
  .step-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #0ea5e9;
    color: white;
    border-radius: 50%;
    width: 28px;
    height: 28px;
    font-size: .8rem;
    font-weight: 700;
    font-family: 'Syne', sans-serif;
    margin-right: .5rem;
    flex-shrink: 0;
  }

  /* Nasconde footer Streamlit */
  footer {visibility: hidden;}
  #MainMenu {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════
#  HERO HEADER
# ══════════════════════════════════════════════

st.markdown("""
<div class="hero">
  <div class="badge">⚡ Powered by GPT-4o</div>
  <h1>📋 Content Brief Generator</h1>
  <p>Analizza i top risultati SERP e genera brief pronti per il tuo copywriter</p>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════
#  CHIAVI API (da Streamlit Secrets o input)
# ══════════════════════════════════════════════

# Prova a caricare da st.secrets (per il deploy), poi da env locale
def get_secret(key):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, "")

SERP_API_KEY  = get_secret("SERP_API_KEY")
OPENAI_KEY    = get_secret("OPENAI_API_KEY")
TARGET_DOMAIN = get_secret("TARGET_DOMAIN")

# Se le chiavi non sono nei secrets, mostra i campi di input
with st.expander("🔑 Configurazione API Keys", expanded=not bool(SERP_API_KEY and OPENAI_KEY)):
    col1, col2 = st.columns(2)
    with col1:
        if not SERP_API_KEY:
            SERP_API_KEY = st.text_input("SERP API Key", type="password",
                                          help="ValueSERP o SerpAPI")
    with col2:
        if not OPENAI_KEY:
            OPENAI_KEY = st.text_input("OpenAI API Key", type="password")
    if not TARGET_DOMAIN:
        TARGET_DOMAIN = st.text_input("Il tuo dominio (da escludere dai risultati)",
                                       placeholder="es. tuosito.com")

st.divider()

# ══════════════════════════════════════════════
#  FORM PRINCIPALE
# ══════════════════════════════════════════════

st.markdown("### ⚙️ Imposta il Brief")

keyword = st.text_input(
    "🎯 Parola chiave target",
    placeholder="es. content marketing B2B",
)

col1, col2 = st.columns(2)
with col1:
    audience = st.text_input(
        "👥 Pubblico di destinazione",
        placeholder="es. Marketing manager di PMI",
        value="SEO manager e content strategist",
    )
with col2:
    goal = st.text_input(
        "🏆 Obiettivo del contenuto",
        placeholder="es. Posizionarsi in top 5 e generare lead",
        value="Posizionarsi per questa keyword e generare lead",
    )

num_results = st.slider("📊 Numero di risultati SERP da analizzare", 3, 10, 8)

st.divider()

# ══════════════════════════════════════════════
#  FUNZIONI CORE
# ══════════════════════════════════════════════

def fetch_serp_results(keyword, num):
    params = {
        "api_key": SERP_API_KEY,
        "q":       keyword,
        "num":     num + 5,
        "gl":      "it",
        "hl":      "it",
        "output":  "json",
    }
    response = requests.get("https://api.valueserp.com/search", params=params, timeout=15)
    if response.status_code != 200:
        params["engine"] = "google"
        response = requests.get("https://serpapi.com/search", params=params, timeout=15)

    data = response.json()
    raw_results = data.get("organic_results", [])
    if not raw_results:
        raise ValueError(f"Nessun risultato trovato. Risposta: {str(data)[:300]}")

    results = []
    for item in raw_results:
        url    = item.get("link") or item.get("url", "")
        domain = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
        if TARGET_DOMAIN and TARGET_DOMAIN.lower() in domain.lower():
            continue
        results.append({
            "position":    item.get("position", len(results) + 1),
            "url":         url,
            "title":       item.get("title", ""),
            "description": item.get("snippet") or item.get("description", ""),
        })
        if len(results) >= num:
            break
    return results


def extract_page_data(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ContentBriefBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    page_title = soup.title.string.strip() if soup.title else ""
    meta_desc  = ""
    meta_tag   = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if meta_tag:
        meta_desc = meta_tag.get("content", "").strip()

    headings = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(separator=" ", strip=True)
        if text:
            headings.append({"level": tag.name.upper(), "text": text})

    word_count = sum(len(t.get_text().split()) for t in soup.find_all(["p", "li"]))

    return {"page_title": page_title, "meta_desc": meta_desc,
            "headings": headings, "word_count": word_count}


def build_serp_summary(pages):
    lines = []
    for p in pages:
        lines.append(f"\n--- Posizione {p['position']} ---")
        lines.append(f"URL: {p['url']}")
        lines.append(f"Titolo SERP: {p['title']}")
        lines.append(f"Snippet: {p['description']}")
        lines.append(f"Title tag: {p.get('page_title', '')}")
        lines.append(f"Parole stimate: ~{p.get('word_count', 0)}")
        lines.append("Heading:")
        for h in p.get("headings", []):
            indent = "  " if h["level"] == "H2" else ("    " if h["level"] == "H3" else "")
            lines.append(f"{indent}{h['level']}: {h['text']}")
    return "\n".join(lines)


def generate_brief(keyword, audience, goal, pages):
    client = OpenAI(api_key=OPENAI_KEY)
    serp_summary = build_serp_summary(pages)

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=4096,
        messages=[
            {
                "role": "system",
                "content": "Sei un senior SEO content strategist. Analizza i dati SERP forniti e produci un brief dettagliato e operativo sui contenuti."
            },
            {
                "role": "user",
                "content": f"""Parola chiave target: {keyword}
Pubblico di destinazione: {audience}
Obiettivo del contenuto: {goal}

Ecco le prime {len(pages)} pagine in classifica:
{serp_summary}

Produci un brief con queste sezioni:

1. ANALISI DELL'INTENTO DI RICERCA: cosa sta cercando l'utente? (~100 parole)
2. FORMATO DEL CONTENUTO CONSIGLIATO: con motivazione.
3. TAG TITOLO SUGGERITI: 3 opzioni sotto i 60 caratteri.
4. META DESCRIZIONI SUGGERITE: 2 opzioni sotto i 155 caratteri.
5. STRUTTURA HEADING CONSIGLIATA: schema H1→H2→H3 completo. Indica argomenti must-cover, segnali forti (3+ pagine) e opportunità di differenziazione.
6. WORD COUNT CONSIGLIATO — con motivazione.
7. ENTITÀ CHIAVE DA INCLUDERE — concetti, strumenti, brand.
8. OPPORTUNITÀ DI LINK INTERNI — [Da compilare a cura del team SEO]
9. NOTE SUL CONTENUTO — tono, profondità, angolazione.

Formatta ogni sezione con il numero e il titolo in MAIUSCOLO."""
            }
        ]
    )
    return response.choices[0].message.content


def brief_to_html(keyword, audience, goal, pages, brief_text):
    date_str  = datetime.now().strftime("%d %B %Y")
    html_body = ""

    for line in brief_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^\d+\.\s+[A-Z][A-Z\s\-—]+$", stripped):
            num, _, title = stripped.partition(". ")
            html_body += f'<h2 class="sec"><span class="n">{num}</span>{title.title()}</h2>\n'
        elif stripped.startswith(("-", "•", "*")):
            html_body += f'<li>{stripped.lstrip("-•* ").strip()}</li>\n'
        elif re.match(r"^(H1|H2|H3):", stripped):
            level, _, content = stripped.partition(": ")
            indent = {"H1": "", "H2": "&nbsp;&nbsp;&nbsp;", "H3": "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"}.get(level, "")
            tag    = {"H1": "h3", "H2": "h4", "H3": "h5"}.get(level, "p")
            html_body += f'<{tag} class="ol-{level.lower()}">{indent}{content}</{tag}>\n'
        else:
            html_body += f'<p>{stripped}</p>\n'

    rows = "".join(
        f'<tr><td>{p["position"]}</td><td><a href="{p["url"]}" target="_blank">{p["title"] or p["url"][:50]}</a></td><td>~{p.get("word_count",0):,}</td></tr>'
        for p in pages
    )

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Content Brief — {keyword}</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{{--blue:#2563eb;--sky:#0ea5e9;--bg:#f8fafc;--card:#fff;--text:#1e293b;--muted:#64748b;--border:#e2e8f0}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);line-height:1.75;padding:2rem 1rem}}
.wrap{{max-width:860px;margin:0 auto}}
.hero{{background:linear-gradient(135deg,#0f172a,#1e3a5f 60%,var(--sky));border-radius:14px;padding:2.5rem;margin-bottom:2rem;color:#fff}}
.hero h1{{font-family:'Syne',sans-serif;font-size:1.9rem;font-weight:800;margin-bottom:.4rem}}
.hero .sub{{opacity:.7;font-size:.95rem}}
.meta{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.75rem;margin-top:1.25rem}}
.mi{{background:rgba(255,255,255,.12);border-radius:8px;padding:.6rem 1rem}}
.mi .l{{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;opacity:.75}}
.mi .v{{font-weight:600;font-size:.92rem}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.75rem 2rem;margin-bottom:1.5rem;box-shadow:0 1px 4px rgba(0,0,0,.04)}}
.card h2{{font-family:'Syne',sans-serif;font-size:1rem;color:var(--muted);margin-bottom:1rem;padding-bottom:.5rem;border-bottom:1px solid var(--border)}}
h2.sec{{font-family:'Syne',sans-serif;font-size:1rem;font-weight:700;color:var(--blue);margin:1.5rem 0 .5rem;display:flex;align-items:center;gap:.5rem}}
.n{{background:var(--blue);color:#fff;border-radius:50%;width:1.55rem;height:1.55rem;display:inline-flex;align-items:center;justify-content:center;font-size:.78rem;flex-shrink:0}}
p{{margin-bottom:.7rem}}
li{{margin-left:1.4rem;margin-bottom:.3rem}}
a{{color:var(--blue);text-decoration:none}}a:hover{{text-decoration:underline}}
.ol-h1{{font-weight:700;margin:.7rem 0 .2rem}}
.ol-h2{{font-weight:500;color:var(--muted);margin:.35rem 0 .15rem}}
.ol-h3{{font-weight:400;font-style:italic;color:var(--muted);margin:.2rem 0}}
table{{width:100%;border-collapse:collapse;font-size:.88rem}}
th{{background:var(--bg);padding:.5rem .75rem;text-align:left;font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}
td{{padding:.5rem .75rem;border-top:1px solid var(--border);vertical-align:top}}
tr:hover td{{background:var(--bg)}}
footer{{text-align:center;margin-top:2rem;font-size:.78rem;color:var(--muted)}}
</style>
</head>
<body>
<div class="wrap">
<div class="hero">
  <h1>📋 Content Brief</h1>
  <div class="sub">Generato il {date_str}</div>
  <div class="meta">
    <div class="mi"><div class="l">Keyword</div><div class="v">{keyword}</div></div>
    <div class="mi"><div class="l">Pubblico</div><div class="v">{audience}</div></div>
    <div class="mi"><div class="l">Obiettivo</div><div class="v">{goal}</div></div>
    <div class="mi"><div class="l">Pagine analizzate</div><div class="v">{len(pages)}</div></div>
  </div>
</div>
<div class="card">
  <h2>📊 Competitor analizzati</h2>
  <table><thead><tr><th>#</th><th>Pagina</th><th>Parole stimate</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>
<div class="card">
  <h2>🧠 Brief generato da AI (GPT-4o)</h2>
  {html_body}
</div>
<footer>Content Brief Generator · {date_str}</footer>
</div></body></html>"""


# ══════════════════════════════════════════════
#  BOTTONE E LOGICA PRINCIPALE
# ══════════════════════════════════════════════

generate_btn = st.button("🚀 Genera Brief", type="primary", use_container_width=True)

if generate_btn:
    # Validazione
    if not keyword:
        st.error("Inserisci una parola chiave target.")
        st.stop()
    if not SERP_API_KEY:
        st.error("Inserisci la SERP API Key.")
        st.stop()
    if not OPENAI_KEY:
        st.error("Inserisci la OpenAI API Key.")
        st.stop()

    # FASE 1
    with st.status("🔍 Recupero risultati SERP…", expanded=True) as status:
        try:
            serp_results = fetch_serp_results(keyword, num_results)
            st.write(f"✅ {len(serp_results)} risultati trovati")
        except Exception as e:
            st.error(f"Errore SERP: {e}")
            st.stop()

        # FASE 2
        status.update(label="📄 Analisi pagine competitor…")
        pages = []
        progress = st.progress(0)
        for i, item in enumerate(serp_results):
            st.write(f"  [{item['position']}] {item['url'][:65]}…")
            page_data = extract_page_data(item["url"])
            if page_data:
                pages.append({**item, **page_data})
                st.write(f"  → {len(page_data['headings'])} heading | ~{page_data['word_count']} parole")
            else:
                pages.append({**item, "page_title": "", "meta_desc": "", "headings": [], "word_count": 0})
            progress.progress((i + 1) / len(serp_results))
            time.sleep(1)

        # FASE 3
        status.update(label="🤖 Generazione brief con GPT-4o…")
        try:
            brief_text = generate_brief(keyword, audience, goal, pages)
            st.write("✅ Brief generato!")
        except Exception as e:
            st.error(f"Errore OpenAI: {e}")
            st.stop()

        status.update(label="✅ Completato!", state="complete")

    # FASE 4 — OUTPUT
    st.divider()
    st.markdown("### 📋 Il tuo Brief")

    # Mostra il testo del brief
    with st.expander("👁 Anteprima testo", expanded=False):
        st.text(brief_text)

    # Genera HTML
    html_content = brief_to_html(keyword, audience, goal, pages, brief_text)

    # Download buttons
    col1, col2 = st.columns(2)

    slug     = re.sub(r"[\s_]+", "-", keyword.lower())
    slug     = re.sub(r"[^\w-]", "", slug)
    date_tag = datetime.now().strftime("%Y-%m-%d")
    filename = f"brief_{slug}_{date_tag}"

    with col1:
        st.download_button(
            label="⬇️ Scarica HTML",
            data=html_content.encode("utf-8"),
            file_name=f"{filename}.html",
            mime="text/html",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            label="⬇️ Scarica TXT",
            data=brief_text.encode("utf-8"),
            file_name=f"{filename}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    # Metriche rapide
    st.divider()
    avg_wc   = int(sum(p.get("word_count", 0) for p in pages) / max(len(pages), 1))
    total_h  = sum(len(p.get("headings", [])) for p in pages)
    c1, c2, c3 = st.columns(3)
    c1.metric("Pagine analizzate", len(pages))
    c2.metric("Media parole competitor", f"~{avg_wc:,}")
    c3.metric("Heading totali estratti", total_h)
