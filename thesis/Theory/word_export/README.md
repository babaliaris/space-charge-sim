# Word export of the Greek thesis

LyX cannot write .docx, so the Word file is made from the LaTeX export with pandoc
(`pip install pypandoc_binary` gives a pandoc binary). Every number (sections, equations,
figures, tables, citations) is taken from a LaTeX build, so it matches the PDF.

Steps (in a work folder with a copy of the .lyx and a link `assets -> thesis/Theory/assets`):

1. `flatpak run --filesystem=<work> --filesystem=<thesis/Theory> org.lyx.LyX -batch -e luatex thesis.lyx`
2. Run `/app/texlive/bin/x86_64-linux/lualatex thesis.tex` twice inside the LyX Flatpak (for .aux/.toc).
3. `python prep.py`: writes `pandoc_in.tex` (numbers resolved, PDF figures as PNG in `img/`,
   `\cancelto` shown as `\underbrace{...}_{=0}`, which Word math does not have).
4. `pandoc pandoc_in.tex -f latex -t docx -o thesis.docx --resource-path=. --toc --toc-depth=3 -M toc-title="Περιεχόμενα" -M lang=el-GR -M title="..." -M author="..." -M date="..."`
5. `python post.py thesis.docx`: page breaks after the title page, the contents and the acknowledgements.
