"""Page breaks after the title page, the contents and the acknowledgements (as in the PDF)."""
import re
import sys
import zipfile

p = sys.argv[1]
z = zipfile.ZipFile(p)
items = [(i, z.read(i.filename)) for i in z.infolist()]
z.close()
BR = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
d = dict((i.filename, b) for i, b in items)["word/document.xml"].decode()


def before(pattern, text):
    m = re.search(pattern, text, flags=re.S)
    return text[:m.start()] + BR + text[m.start():] if m else text


d = before(r"<w:sdt>", d)
for h in ("Ευχαριστίες", "Εισαγωγή"):
    d = before(r'<w:p>(?:(?!</w:p>).)*?w:val="Heading1"(?:(?!</w:p>).)*?>' + h + "<", d)
out = p + ".tmp"
zo = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
for i, b in items:
    zo.writestr(i, d.encode() if i.filename == "word/document.xml" else b)
zo.close()
import os
os.replace(out, p)
print("page breaks:", d.count('w:type="page"'))
