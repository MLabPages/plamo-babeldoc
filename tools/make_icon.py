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
d.rounded_rectangle((118, 96, S - 118, S - 96), radius=26, fill=(255, 253, 248, 255))
font = None
for f in ("C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/meiryob.ttc", "C:/Windows/Fonts/msgothic.ttc"):
    if Path(f).exists():
        font = ImageFont.truetype(f, 220)
        break
d.text((S / 2, S / 2 + 6), "訳", font=font, fill=(180, 83, 42, 255), anchor="mm")
img.save(out / "app.png")
img.save(out / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out / "app.ico")
