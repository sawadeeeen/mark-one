from PIL import Image, ImageDraw

# 32x32のアイコンを作成
size = (32, 32)
image = Image.new('RGBA', size, (0, 0, 0, 0))
draw = ImageDraw.Draw(image)

# シンプルな青い四角を描画
draw.rectangle([4, 4, 28, 28], fill=(0, 120, 212))

# アイコンとして保存
image.save('app.ico', format='ICO') 