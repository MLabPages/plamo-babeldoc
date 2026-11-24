"""アプリのアイコン（assets/app.ico）を作る。"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
out = ROOT / "assets"
out.mkdir(exist_ok=True)
S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, S - 16, S - 16), radius=110, fill=(180, 83, 42, 255))
d.rounded_rectangle((86, 78, 356, 410), radius=26, fill=(255, 253, 248, 255))
for y, xend in ((126, 300), (166, 300), (206, 242)):
    d.rounded_rectangle((126, y, xend, y + 14), radius=7, fill=(199, 171, 150, 255))
d.rounded_rectangle((216, 230, 444, 446), radius=50, fill=(30, 83, 92, 255), outline=(255, 253, 248, 255), width=12)
font = None
for f in ("C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/meiryob.ttc", "C:/Windows/Fonts/msgothic.ttc"):
    if Path(f).exists():
        font = ImageFont.truetype(f, 144)
        break
# Center the rendered letter, rather than the font's line box.
mask = Image.new("L", (S, S))
ImageDraw.Draw(mask).text((S // 2, S // 2), "M", font=font, fill=255, anchor="mm")
letter = mask.crop(mask.getbbox())
img.paste((255, 253, 248, 255),
          (330 - letter.width // 2, 338 - letter.height // 2), letter)
img.save(out / "app.png")
img.resize((192, 192), Image.Resampling.LANCZOS).save(ROOT / "paperapp" / "static" / "icon.png")
img.save(out / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out / "app.ico")
