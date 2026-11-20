"""
Export the charts of Excel workbooks as vector PDF figures for the LyX write-up.

You make and style the charts in Excel (or ONLYOFFICE); this script redraws each
chart with LaTeX/pgfplots, so the figures are vector graphics that use the same
fonts as the thesis. It reads, for every chart: the series and the cell ranges
they come from, the series names, line colours and dashes, the axis titles and
the axis limits you set. The data are read from the cells, so an exported figure
always matches the workbook as last saved.

The chart TITLE is not drawn, because in LyX the figure caption plays that role.
The title is printed when the script runs, so it can be reused as the caption.

How to run (from the repository root; needs pdflatex with pgfplots):

    python -m thesis.export_excel_charts                      # every workbook in thesis/excel/
    python -m thesis.export_excel_charts thesis/excel/wh_fig3_reproduction.xlsx
    python -m thesis.export_excel_charts --output-dir thesis/Theory/assets/plots --width 14cm --height 8cm
    python -m thesis.export_excel_charts --lang el            # Greek labels -> thesis/Theory/assets/plots/greek/

The Greek version translates the axis titles and the words in the legends with the GREEK table
below (symbols such as E_sp, t, V and the units stay as they are). It needs a TeX with Greek
support: it uses LuaLaTeX with the CMU Serif font from the LyX Flatpak (org.lyx.LyX) when that is
installed, otherwise a lualatex on the PATH that can find CMU Serif.

Each chart becomes  <output-dir>/<workbook name>_chart<N>.pdf, numbered by sheet and by
position on the sheet (top to bottom, left to right), so the names stay the same
when you edit a chart's title.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import openpyxl
from openpyxl.utils.cell import range_boundaries

# =============================================================================
# INPUTS (defaults, all can be changed on the command line)
# =============================================================================
INPUT_FOLDER  = "thesis/excel"                   # workbooks to export when no file is given
OUTPUT_FOLDER = "thesis/Theory/assets/plots"     # where the PDF figures are written
FIGURE_WIDTH  = "14cm"                    # size of the plot area in the PDF
FIGURE_HEIGHT = "8cm"

# Greek translations of the chart texts (--lang el). Whole axis titles first, then legend phrases.
GREEK = {
    "Applied electric field [kV/cm]": "Εφαρμοζόμενο ηλεκτρικό πεδίο [kV/cm]",
    "Total electric field [kV/cm]": "Συνολικό ηλεκτρικό πεδίο [kV/cm]",
    "Electric field [kV/cm]": "Ηλεκτρικό πεδίο [kV/cm]",
    "Distance z from the rod tip [cm]": "Απόσταση z από την κορυφή της ακίδας [cm]",
    "Time to crest [us]": "Χρόνος μετώπου [us]",
    "Inception voltage [kV]": "Τάση έναυσης [kV]",
    "Streamer length [cm]": "Μήκος νηματίου [cm]",
    "Streamer charge [nC]": "Φορτίο νηματίου [nC]",
    ", paper measured": ", δημοσίευση: μέτρηση",
    "Applied Electric Field [kV/cm]": "Εφαρμοζόμενο ηλεκτρικό πεδίο [kV/cm]",
    "Total Electric Field [kV/cm]": "Συνολικό ηλεκτρικό πεδίο [kV/cm]",
    "Electric Field [kV/cm]": "Ηλεκτρικό πεδίο [kV/cm]",
    "Electric Field (kV/cm)": "Ηλεκτρικό πεδίο (kV/cm)",
    "Distance (z) from the rod tip [cm]": "Απόσταση (z) από την κορυφή της ακίδας [cm]",
    "Distance from the rod tip (cm)": "Απόσταση από την κορυφή της ακίδας (cm)",
    "Distance from the rod-tip (z) in cm": "Απόσταση (z) από την κορυφή της ακίδας σε cm",
    "z [cm] from the rod tip": "z [cm] από την κορυφή της ακίδας",
    " after 2nd-streamer criterion": " μετά το κριτήριο 2ου νηματίου",
    " before drift": " πριν από την ολίσθηση",
    " after drift": " μετά την ολίσθηση",
    " inception": " έναυση",
    "Time to crest (us)": "Χρόνος μετώπου (us)",
    "Inception voltage (kV)": "Τάση έναυσης (kV)",
    "Streamer length (cm)": "Μήκος νηματίου (cm)",
    "Streamer charge (nC)": "Φορτίο νηματίου (nC)",
    "first streamer": "πρώτο νημάτιο",
    "second streamer": "δεύτερο νημάτιο",
    "max ": "μέγιστο ",
    "E_ex applied": "E_ex εφαρμοζόμενο",
    " (this work)": " (αυτή η εργασία)",
    ", paper calculated": ", δημοσίευση: υπολογισμός",
    ", paper experimental": ", δημοσίευση: πείραμα",
    "measured (paper)": "μέτρηση (δημοσίευση)",
    " (paper)": " (δημοσίευση)",
    " fit": " προσαρμογή",
    "this work": "αυτή η εργασία",
    "streamer 1": "νημάτιο 1",
    "streamer 2": "νημάτιο 2",
}

NS = {
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
}
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

# Office default theme, used when the workbook has no theme part
DEFAULT_ACCENTS = {"accent1": "4472C4", "accent2": "ED7D31", "accent3": "A5A5A5",
                   "accent4": "FFC000", "accent5": "5B9BD5", "accent6": "70AD47"}

# Excel dash names -> pgfplots dash styles
DASHES = {"dash": "dashed", "sysDash": "dashed", "lgDash": "dashed", "dashDot": "dashdotted",
          "lgDashDot": "dashdotted", "sysDot": "dotted", "dot": "dotted", "sysDashDot": "dashdotted"}


# =============================================================================
# Reading the workbook
# =============================================================================
def find(node, path):
    """node.find(path), with a clear error if the chart XML lacks the element."""
    found = node.find(path, NS)
    if found is None:
        raise ValueError(f"element {path} not found in the chart XML")
    return found


def attribute(node, name):
    """node.get(name), with a clear error if the attribute is missing."""
    value = node.get(name)
    if value is None:
        raise ValueError(f"attribute {name} missing on <{node.tag}>")
    return value


def theme_accents(z):
    """Accent colours of the workbook theme (hex strings)."""
    names = [n for n in z.namelist() if n.startswith("xl/theme/")]
    if not names:
        return dict(DEFAULT_ACCENTS)
    root = ET.fromstring(z.read(names[0]))
    accents = dict(DEFAULT_ACCENTS)
    for key in DEFAULT_ACCENTS:
        node = root.find(f".//a:clrScheme/a:{key}", NS)
        if node is not None:
            colour = node.find("a:srgbClr", NS)
            if colour is not None:
                accents[key] = attribute(colour, "val")
    return accents


def part_path(target):
    """Package path of a relationship target: Excel writes "../drawings/x.xml", openpyxl "/xl/drawings/x.xml"."""
    return target.lstrip("/") if target.startswith("/xl/") else "xl/" + target.replace("../", "")


def charts_in_order(z):
    """Chart XML paths, ordered by sheet and by position on the sheet."""
    workbook = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {attribute(r, "Id"): attribute(r, "Target") for r in rels}
    sheets = [s for s in workbook.iter() if s.tag.endswith("}sheet")]

    ordered = []
    for sheet in sheets:
        target = rid_to_target[attribute(sheet, f"{{{NS['r']}}}id")]
        sheet_path = target.lstrip("/") if target.startswith("/xl/") else "xl/" + target
        sheet_rels = sheet_path.replace("worksheets/", "worksheets/_rels/") + ".rels"
        if sheet_rels not in z.namelist():
            continue
        for rel in ET.fromstring(z.read(sheet_rels)):
            if not attribute(rel, "Type").endswith("/drawing"):
                continue
            drawing = part_path(attribute(rel, "Target"))
            drawing_rels = drawing.replace("drawings/", "drawings/_rels/") + ".rels"
            targets = {attribute(r, "Id"): part_path(attribute(r, "Target"))
                       for r in ET.fromstring(z.read(drawing_rels))}
            anchors = []
            for anchor in ET.fromstring(z.read(drawing)):
                start = anchor.find("xdr:from", NS)
                row = int(find(start, "xdr:row").text or 0) if start is not None else 0
                col = int(find(start, "xdr:col").text or 0) if start is not None else 0
                chart = anchor.find(".//c:chart", NS)
                if chart is not None:
                    anchors.append((row, col, targets[attribute(chart, f"{{{NS['r']}}}id")]))
            ordered += [path for _, _, path in sorted(anchors)]
    return ordered


def rich_text(node):
    """Plain text of a <c:title> or <c:tx> element."""
    if node is None:
        return ""
    return "".join(t.text or "" for t in node.iter(f"{{{NS['a']}}}t")).strip()


def read_range(workbook, formula):
    """Values of a cell range such as  'Fig5a applied'!$B$2:$B$302  (None for empty cells)."""
    sheet, cells = formula.rsplit("!", 1)
    sheet = sheet.strip("'").replace("''", "'")
    ws = workbook[sheet]
    min_col, min_row, max_col, max_row = range_boundaries(cells.replace("$", ""))
    values = []
    for row in ws.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col, values_only=True):
        values += list(row)
    return values


def line_style(ser, accents):
    """Colour, width and dash of a series line."""
    colour, width, dash = None, 1.5, None
    line = ser.find("c:spPr/a:ln", NS)
    if line is not None:
        if line.get("w"):
            width = int(line.get("w")) / 12700.0           # EMU -> pt
        srgb = line.find("a:solidFill/a:srgbClr", NS)
        scheme = line.find("a:solidFill/a:schemeClr", NS)
        if srgb is not None:
            colour = srgb.get("val")
        elif scheme is not None:
            colour = accents.get(scheme.get("val"))
        dash_node = line.find("a:prstDash", NS)
        if dash_node is not None:
            dash = DASHES.get(dash_node.get("val"))
        if line.find("a:noFill", NS) is not None:
            width = 0
    return colour, width, dash


def read_chart(z, path, workbook, accents):
    root = ET.fromstring(z.read(path))
    chart = find(root, "c:chart")
    info = {"title": rich_text(chart.find("c:title", NS)), "series": [], "axes": {}}

    legend = chart.find("c:legend/c:legendPos", NS)
    info["legend"] = legend.get("val") if legend is not None else None

    for ax in find(chart, "c:plotArea"):
        if not ax.tag.endswith(("}valAx", "}catAx")):
            continue
        pos = attribute(find(ax, "c:axPos"), "val")
        scaling = find(ax, "c:scaling")
        limits = {}
        for key in ("min", "max"):
            node = scaling.find(f"c:{key}", NS)
            if node is not None:
                limits[key] = float(attribute(node, "val"))
        if scaling.find("c:logBase", NS) is not None:
            limits["log"] = True
        info["axes"]["x" if pos in ("b", "t") else "y"] = {"label": rich_text(ax.find("c:title", NS)), **limits}

    for ser in chart.iter(f"{{{NS['c']}}}ser"):
        name_ref = ser.find("c:tx/c:strRef/c:f", NS)
        name_cache = ser.find("c:tx/c:strRef/c:strCache/c:pt/c:v", NS)
        name = ser.find("c:tx/c:v", NS)
        if name_cache is not None:
            name = name_cache.text
        elif name_ref is not None:
            name = next((v for v in read_range(workbook, name_ref.text) if v), "")
        else:
            name = name.text if name is not None else ""
        x_ref = ser.find("c:xVal//c:f", NS)
        y_ref = ser.find("c:yVal//c:f", NS)
        if x_ref is None or y_ref is None:
            print(f"   (skipping a series without x/y ranges in {path})")
            continue
        points = [(x, y) for x, y in zip(read_range(workbook, x_ref.text), read_range(workbook, y_ref.text))
                  if isinstance(x, (int, float)) and isinstance(y, (int, float))]
        colour, width, dash = line_style(ser, accents)
        if colour is None:                         # markers-only series: take the marker's colour
            fill = ser.find("c:marker/c:spPr/a:solidFill/a:srgbClr", NS)
            colour = fill.get("val") if fill is not None else None
        marker = ser.find("c:marker/c:symbol", NS)
        info["series"].append({"name": str(name), "points": points, "colour": colour, "width": width,
                               "dash": dash, "marker": marker is not None and marker.get("val") != "none"})
    return info


# =============================================================================
# Writing LaTeX
# =============================================================================
def translate(text, lang):
    """Replace the English chart texts with their Greek translation (GREEK table)."""
    if lang != "el":
        return text
    for en in sorted(GREEK, key=len, reverse=True):
        text = text.replace(en, GREEK[en])
    return text


def latex_text(text, legend=False):
    """Make a chart label safe for LaTeX and typeset field symbols such as E_sp or E_I,rod."""
    text = str(text)
    if legend:                                                  # the unit is already on the axis
        stripped = re.sub(r"\s*\[(kV/cm|kV|cm|nC|us)\]\s*$", "", text)
        text = stripped if not re.fullmatch(r"[0-9.]+", stripped) else stripped + " kV/cm"
    pieces = []
    for token in re.split(r"(\b[EVQL]_[A-Za-z0-9,]+|\bE[a-z]+,[a-z,]+\b|(?<![\u0370-\u03ff\u1f00-\u1fff])[Δμθ](?![\u0370-\u03ff\u1f00-\u1fff])|\bus\b)", text):
        if not token:
            continue
        if re.fullmatch(r"[EVQL]_[A-Za-z0-9,]+", token):
            pieces.append("$" + token[0] + r"_{\mathrm{" + token[2:].replace(",", ",\\,") + "}}$")
        elif re.fullmatch(r"E[a-z]+,[a-z,]+", token):             # e.g. Esp,wh  Ei,rod,wh
            pieces.append(r"$E_{\mathrm{" + token[1:].replace(",", ",\\,") + "}}$")
        elif token in ("Δ", "μ", "θ"):
            pieces.append({"Δ": r"$\Delta$", "μ": r"$\mu$", "θ": r"$\theta$"}[token])
        elif token == "us":
            pieces.append(r"$\mu$s")
        else:
            for ch, rep in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("#", r"\#"),
                            ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\~{}"), ("^", r"\^{}")):
                token = token.replace(ch, rep)
            pieces.append(token)
    return "".join(pieces)


def chart_to_tex(info, width, height, lang="en"):
    x, y = info["axes"].get("x", {}), info["axes"].get("y", {})
    x = {**x, "label": translate(x.get("label", ""), lang)}
    y = {**y, "label": translate(y.get("label", ""), lang)}
    options = [f"width={width}", f"height={height}", "scale only axis", "grid=major",
               "grid style={black!12}", "axis line style={black!40}", "tick style={black!40}",
               "every axis label/.append style={font=\\small}", "tick label style={font=\\footnotesize}",
               "legend style={font=\\footnotesize, draw=none, fill=none, legend cell align=left}",
               f"xlabel={{{latex_text(x.get('label', ''))}}}", f"ylabel={{{latex_text(y.get('label', ''))}}}",
               "scaled ticks=false", "tick label style={/pgf/number format/fixed}",
               "enlarge x limits=false", "enlarge y limits=0.03"]
    for axis, spec in (("x", x), ("y", y)):
        for key in ("min", "max"):
            if key in spec:
                options.append(f"{axis}{key}={spec[key]:g}")
        if spec.get("log"):
            options.append(f"{axis}mode=log")
            options.append(f"log ticks with fixed point, {axis}tick={{10,15,20,30,50,100,200,300,500,1000}}")
    if info["legend"] in ("b", None):
        n = len(info["series"])
        options.append(f"legend columns={2 if n > 3 else n}")
        options.append("legend style={at={(0.5,-0.18)}, anchor=north, /tikz/every even column/.append style={column sep=1em}}")
    elif info["legend"] == "r":
        options.append("legend pos=outer north east")
    elif info["legend"] == "t":
        options.append("legend style={at={(0.5,1.03)}, anchor=south}")

    if lang == "el":       # Unicode font with Greek, the same as the Greek LyX document
        fonts = [r"\usepackage{fontspec}", r"\setmainfont{CMU Serif}"]
    else:
        fonts = [r"\usepackage[utf8]{inputenc}", r"\usepackage[T1]{fontenc}", r"\usepackage{lmodern}"]
    lines = [r"\documentclass{standalone}"] + fonts + [r"\usepackage{pgfplots}", r"\pgfplotsset{compat=1.18}",
             r"\begin{document}", r"\begin{tikzpicture}", r"\begin{axis}[" + ",\n  ".join(options) + "]"]
    for i, s in enumerate(info["series"]):
        style = ["mark=*" if s["marker"] else "no markers", f"line width={max(s['width'] * 0.6, 0.4):.2f}pt"]
        if s["width"] == 0:                        # markers only (line switched off in Excel)
            style = ["only marks", "mark=triangle*", "line width=0.4pt"]
        if s["colour"]:
            lines.append(rf"\definecolor{{series{i}}}{{HTML}}{{{s['colour'].upper()}}}")
            style.append(f"color=series{i}")
        if s["dash"]:
            style.append(s["dash"])
        if s["marker"]:
            style.append("mark size=1pt" if s["width"] else "mark size=1.8pt")
        coordinates = " ".join(f"({px:.6g},{py:.6g})" for px, py in s["points"])
        lines.append(rf"\addplot[{', '.join(style)}] coordinates {{{coordinates}}};")
        lines.append(rf"\addlegendentry{{{latex_text(translate(s['name'], lang), legend=True)}}}")
    lines += [r"\end{axis}", r"\end{tikzpicture}", r"\end{document}"]
    return "\n".join(lines)


# =============================================================================
# Main
# =============================================================================
def latex_command(lang, workdir):
    """Command that compiles chart.tex in workdir: pdflatex for English, LuaLaTeX with Greek fonts for Greek."""
    if lang != "el":
        return ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "chart.tex"]
    has_lyx_flatpak = shutil.which("flatpak") and subprocess.run(
        ["flatpak", "info", "org.lyx.LyX"], capture_output=True, check=False).returncode == 0
    if has_lyx_flatpak:
        return ["flatpak", "run", f"--filesystem={workdir}", "--env=LC_ALL=C.UTF-8", "--command=sh", "org.lyx.LyX",
                "-c", ('export PATH=/app/texlive/bin/x86_64-linux:$PATH; cd "$0" && '
                       'exec lualatex -interaction=nonstopmode -halt-on-error chart.tex'), str(workdir)]
    return ["lualatex", "-interaction=nonstopmode", "-halt-on-error", "chart.tex"]


def export_workbook(path, output_dir, width, height, lang="en"):
    print(f"\n{path}")
    z = zipfile.ZipFile(path)
    workbook = openpyxl.load_workbook(path, data_only=True)
    accents = theme_accents(z)
    exported = []
    for number, chart_path in enumerate(charts_in_order(z), start=1):
        info = read_chart(z, chart_path, workbook, accents)
        name = f"{path.stem}_chart{number}.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            tex = Path(tmp) / "chart.tex"
            tex.write_text(chart_to_tex(info, width, height, lang), encoding="utf-8")
            result = subprocess.run(latex_command(lang, tmp), cwd=tmp, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                print(f"   FAILED {name}:\n" + "\n".join(result.stdout.splitlines()[-15:]))
                continue
            shutil.copy(Path(tmp) / "chart.pdf", output_dir / name)
        print(f"   {output_dir / name}\n      title: {info['title'] or '(none)'}  [{len(info['series'])} series]")
        exported.append(output_dir / name)
    return exported


def main():
    parser = argparse.ArgumentParser(description="Export Excel charts as vector PDF figures (pgfplots).")
    parser.add_argument("workbooks", nargs="*", help=f"xlsx files (default: every .xlsx in {INPUT_FOLDER}/)")
    parser.add_argument("--lang", choices=["en", "el"], default="en", help="label language (el = Greek)")
    parser.add_argument("--output-dir", default=None, help=f"default: {OUTPUT_FOLDER} (Greek: {OUTPUT_FOLDER}/greek)")
    parser.add_argument("--width", default=FIGURE_WIDTH)
    parser.add_argument("--height", default=FIGURE_HEIGHT)
    args = parser.parse_args()

    if args.lang == "en" and shutil.which("pdflatex") is None:
        sys.exit("pdflatex was not found. Install a TeX distribution with pgfplots.")
    workbooks = [Path(w) for w in args.workbooks] or sorted(Path(INPUT_FOLDER).glob("*.xlsx"))
    workbooks = [w for w in workbooks if not w.name.startswith(("~$", ".~lock"))]
    output_dir = Path(args.output_dir or (OUTPUT_FOLDER + ("/greek" if args.lang == "el" else "")))
    output_dir.mkdir(parents=True, exist_ok=True)

    total = sum(len(export_workbook(w, output_dir, args.width, args.height, args.lang)) for w in workbooks)
    print(f"\nDone: {total} figure(s) written to {output_dir}/")


if __name__ == "__main__":
    main()
