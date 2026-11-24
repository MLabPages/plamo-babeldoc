"""Generate the Windows and web icons for MLab Paper Reader."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
img = Image.new("RGBA", (512, 512))
draw = ImageDraw.Draw(img)
ink = "#173e45"
paper = "#fff8e9"
draw.rounded_rectangle((16, 16, 496, 496), radius=106, fill=ink)
draw.rounded_rectangle((99, 103, 413, 414), radius=33, fill=paper)
draw.line((153, 163, 359, 163), fill="#d6b68c", width=16)
draw.line((153, 359, 359, 359), fill="#d6b68c", width=16)
draw.line([(149, 319), (149, 213), (207, 276), (265, 213), (265, 319)],
          fill=ink, width=24, joint="curve")
draw.line([(309, 213), (309, 319), (370, 319)], fill=ink, width=24, joint="curve")
img.save(ROOT / "assets" / "app.png")
img.save(ROOT / "assets" / "app.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
img.resize((192, 192), Image.Resampling.LANCZOS).save(ROOT / "paperapp" / "static" / "icon.png")
