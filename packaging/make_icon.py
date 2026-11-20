"""Draw the application icon (rod tip, space-charge cone, plane) -> app/icon.png and packaging/icon.ico."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

fig = plt.figure(figsize=(2.56, 2.56), dpi=100)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
ax.add_patch(FancyBboxPatch((0.04, 0.04), 0.92, 0.92, boxstyle="round,pad=0,rounding_size=0.18", fc="#1B1F3B", ec="none"))
ax.add_patch(Polygon([(0.5, 0.66), (0.22, 0.24), (0.78, 0.24)], closed=True, fc="#4B3FA8", ec="none", alpha=0.95))
ax.add_patch(Polygon([(0.5, 0.66), (0.36, 0.45), (0.64, 0.45)], closed=True, fc="#8E83E8", ec="none"))
ax.add_patch(Rectangle((0.44, 0.70), 0.12, 0.2, fc="#C9CCDA", ec="none"))
ax.add_patch(Circle((0.5, 0.70), 0.06, fc="#C9CCDA", ec="none"))
ax.add_patch(Rectangle((0.14, 0.13), 0.72, 0.06, fc="#D9780F", ec="none"))
png = os.path.join(ROOT, "app", "icon.png")
fig.savefig(png, transparent=True)
Image.open(png).save(os.path.join(HERE, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(png)
