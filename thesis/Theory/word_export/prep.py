"""Prepare the LyX LaTeX export of the Greek thesis for pandoc: resolve every number from the LaTeX build
(.aux/.toc) so the Word file shows the same section, equation, figure, table and citation numbers as the PDF."""
import os
import re
import subprocess

W = os.path.dirname(os.path.abspath(__file__))
tex = open(os.path.join(W, "thesis.tex"), encoding="utf-8").read()
aux = open(os.path.join(W, "thesis.aux"), encoding="utf-8").read()
toc = open(os.path.join(W, "thesis.toc"), encoding="utf-8").read()

GREEK = {1: "Αʹ", 2: "Βʹ", 3: "Γʹ", 4: "Δʹ", 5: "Εʹ", 6: "Ϛʹ", 7: "Ζʹ", 8: "Ηʹ", 9: "Θʹ"}


def group(text, i):
    """Balanced {...} starting at text[i] == '{'; returns (content, index after it)."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
    raise ValueError("unbalanced")


raw = {}
for m in re.finditer(r"\\newlabel\{([^}]*)\}\{", aux):
    outer, _ = group(aux, m.end() - 1)
    first, _ = group(outer, 0)
    raw[m.group(1)] = first


def clean(v, depth=0):
    v = re.sub(r"\\Greeknumeral\s*\{(\d+)\}", lambda g: GREEK[int(g.group(1))], v)
    v = re.sub(r"\\ref\s*\{([^}]*)\}", lambda g: clean(raw.get(g.group(1), "??"), depth + 1) if depth < 5 else "??", v)
    return v.replace("{", "").replace("}", "").strip()


labels = {k: clean(v) for k, v in raw.items()}
bib = dict(re.findall(r"\\bibcite\{([^}]*)\}\{([^}]*)\}", aux))
body = tex[tex.index("\\begin{document}") + len("\\begin{document}"):tex.index("\\end{document}")]

# ---- sections: numbers from the toc, in order ---------------------------------------------
nums = []
for m in re.finditer(r"\\contentsline \{(section|subsection|subsubsection)\}\{\\numberline \{", toc):
    nums.append((m.group(1), clean(group(toc, m.end() - 1)[0])))
it = iter(nums)


def sec(m):
    kind = m.group(1)
    k, n = next(it)
    assert k == kind, (k, kind, m.group(0)[:60])
    return f"\\{kind}*{{{n}. "


body = re.sub(r"\\(section|subsection|subsubsection)\{", sec, body)
assert next(it, None) is None, "toc and sections out of step"
body = body.replace("\\addsec{", "\\section*{").replace("\\appendix", "")

# ---- equations: sequential counter, checked against the labels -----------------------------
count = [0]
bad = []


def number_eq(inner, label_check=True):
    tag = re.search(r"\\tag\{((?:\\ref\{[^}]*\}[,\s]*)+)\}", inner)
    if tag:
        n = ", ".join(labels[k] for k in re.findall(r"\\ref\{([^}]*)\}", tag.group(1)))
        inner = inner.replace(tag.group(0), "")
    else:
        count[0] += 1
        n = str(count[0])
        lab = re.search(r"\\label\{([^}]*)\}", inner)
        if lab and labels.get(lab.group(1)) != n:
            bad.append((lab.group(1), labels.get(lab.group(1)), n))
    inner = re.sub(r"\\label\{[^}]*\}", "", inner).strip()
    return inner, n


def eq(m):
    inner, n = number_eq(m.group(1))
    return f"\\[\n{inner}\\qquad\\text{{({n})}}\n\\]"


def align(m):           # numbered lines are those without \\nonumber
    lines = [ln for ln in re.split(r"\\\\", m.group(1)) if ln.strip()]
    nums = []
    for ln in lines:
        if "\\nonumber" not in ln and "\\notag" not in ln:
            count[0] += 1
            nums.append(str(count[0]))
    inner = "\\\\".join(re.sub(r"\\nonumber|\\notag|\\label\{[^}]*\}", "", ln) for ln in lines)
    tag = f"\\qquad\\text{{({', '.join(nums)})}}" if nums else ""
    return f"\\[\n\\begin{{aligned}}{inner}\\end{{aligned}}{tag}\n\\]"


body = re.sub(r"\\begin\{(?:equation|align)\}(.*?)\\end\{(?:equation|align)\}",
              lambda m: align(m) if m.group(0).startswith("\\begin{align}") else eq(m), body, flags=re.S)
print("equations numbered:", count[0], "mismatches:", bad[:5])

# ---- \\cancelto{a}{b} (not in Word math) -> \\underbrace{b}_{=a} ----------------------------------
def uncancel(text):
    out, i = [], 0
    while True:
        j = text.find("\\cancelto{", i)
        if j < 0:
            return "".join(out) + text[i:]
        a, k = group(text, j + len("\\cancelto"))
        b, k = group(text, k)
        out.append(text[i:j] + f"\\underbrace{{{uncancel(b)}}}_{{={a}}}")
        i = k


body = uncancel(body)
body = re.sub(r"\\cancel\{", r"\\underbrace{", body)

# ---- cross-references ----------------------------------------------------------------------
NAMES = {"fig": ("σχήμα", "σχήματα", "Σχήμα", "Σχήματα"), "tab": ("πίνακα", "πίνακες", "Πίνακα", "Πίνακες"),
         "sec": ("ενότητα", "ενότητες", "Ενότητα", "Ενότητες"), "eq": ("εξίσωση", "εξισώσεις", "Εξίσωση", "Εξισώσεις")}


def refstyle(m):
    raw, keys = m.group(1), [k.strip() for k in m.group(2).split(",")]
    cap, kind = raw[0].isupper(), raw.lower()
    ns = [labels.get(f"{kind}:{k}", "??") for k in keys]
    if kind == "eq":
        ns = [f"({n})" for n in ns]
    one, many, One, Many = NAMES[kind]
    word = (One if cap else one) if len(ns) == 1 else (Many if cap else many)
    text = ns[0] if len(ns) == 1 else (" και ".join(ns) if len(ns) == 2 else ", ".join(ns[:-1]) + " και " + ns[-1])
    return f"{word} {text}"


body = re.sub(r"\\(fig|Fig|tab|Tab|sec|Sec|eq|Eq)ref\{([^}]*)\}", refstyle, body)
body = re.sub(r"\\eqref\{([^}]*)\}", lambda m: f"({labels.get(m.group(1), '??')})", body)
body = re.sub(r"\\ref\{([^}]*)\}", lambda m: labels.get(m.group(1), "??"), body)
body = re.sub(r"\\cite(?:\[[^]]*\])?\{([^}]*)\}",
              lambda m: "[" + ", ".join(bib.get(k.strip(), "?") for k in m.group(1).split(",")) + "]", body)
print("unresolved refs:", body.count("??"))

# ---- figures and tables: numbered captions, PNG images -------------------------------------
os.makedirs(os.path.join(W, "img"), exist_ok=True)
TEXTWIDTH_PT = 17 / 2.54 * 72


def caption_num(m, word):
    env = m.group(0)
    lab = re.search(r"\\label\{([^}]*)\}", env)
    n = labels.get(lab.group(1), "?") if lab else "?"
    env = re.sub(r"\\caption\{", f"\\\\caption{{{word} {n}: ", env, count=1)
    return re.sub(r"\\label\{[^}]*\}", "", env)


body = re.sub(r"\\begin\{figure\}.*?\\end\{figure\}", lambda m: caption_num(m, "Σχήμα"), body, flags=re.S)
body = re.sub(r"\\begin\{table\}.*?\\end\{table\}", lambda m: caption_num(m, "Πίνακας"), body, flags=re.S)


def image(m):
    opts, path = m.group(1) or "", m.group(2)
    src = os.path.join(W, path)
    if not os.path.splitext(src)[1]:
        src += ".pdf" if os.path.exists(src + ".pdf") else ".png"
    name = re.sub(r"[^A-Za-z0-9_]", "_", os.path.splitext(path)[0]) + ".png"
    dst = os.path.join(W, "img", name)
    if src.endswith(".pdf"):
        if not os.path.exists(dst):
            subprocess.run(["pdftoppm", "-r", "200", "-png", "-singlefile", src, dst[:-4]], check=True)
        info = subprocess.run(["pdfinfo", src], capture_output=True, text=True).stdout
        w_pt = float(re.search(r"Page size:\s+([\d.]+)", info).group(1))
    else:
        import shutil
        shutil.copy(src, dst)
        w_pt = TEXTWIDTH_PT
    frac = None
    if "columnwidth" in opts or "linewidth" in opts or "textwidth" in opts:
        f = re.search(r"width=([\d.]*)\\", opts)
        frac = float(f.group(1) or 1) if f else 1.0
    elif "scale=" in opts:
        frac = float(re.search(r"scale=([\d.]+)", opts).group(1)) * w_pt / TEXTWIDTH_PT
    else:
        frac = w_pt / TEXTWIDTH_PT
    frac = min(frac, 1.0)
    return f"\\includegraphics[width={frac:.3f}\\textwidth]{{img/{name}}}"


body = re.sub(r"\\includegraphics(?:\[([^]]*)\])?\{([^}]*)\}", image, body)

# ---- bibliography --------------------------------------------------------------------------
def biblio(m):
    items = re.split(r"\\bibitem(?:\[[^]]*\])?\{([^}]*)\}", m.group(1))[1:]
    out = ["\\section*{Βιβλιογραφία}"]
    for key, text in zip(items[0::2], items[1::2]):
        out.append(f"[{bib.get(key, '?')}] {text.strip()}\n")
    return "\n\n".join(out)


body = re.sub(r"\\begin\{thebibliography\}\{[^}]*\}(.*?)\\end\{thebibliography\}", biblio, body, flags=re.S)
body = re.sub(r"\\begin\{doublespace\}|\\end\{doublespace\}", "", body)
body = body.replace("\\maketitle", "").replace("\\tableofcontents", "")

title = re.search(r"\\title\{(.*?)\}\n", tex, flags=re.S)
author = re.search(r"\\author\{(.*?)\}\n", tex, flags=re.S)
date = re.search(r"\\date\{(.*?)\}\n", tex, flags=re.S)
head = ("\\documentclass{article}\n\\usepackage{amsmath}\n\\usepackage{graphicx}\n"
        + (f"\\title{{{title.group(1)}}}\n" if title else "") + (f"\\author{{{author.group(1)}}}\n" if author else "")
        + (f"\\date{{{date.group(1)}}}\n" if date else "") + "\\begin{document}\n")
open(os.path.join(W, "pandoc_in.tex"), "w", encoding="utf-8").write(head + body + "\n\\end{document}\n")
print("written pandoc_in.tex")
