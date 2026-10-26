"""A blank system splash or cropped/replaced artwork is not launch evidence."""
from PIL import Image, ImageDraw
from scripts.android_opening_capture import matches_opening


def artwork():
    image = Image.new('RGB', (80, 160), 'black')
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 40, 60, 100), fill=(0, 200, 240))
    draw.rectangle((5, 120, 75, 124), fill='white')
    draw.line((0, 0, 15, 15), fill=(0, 30, 60), width=3)
    return image


def test_full_artwork_and_letterboxing_match_but_black_crop_and_bars_do_not():
    source = artwork()
    assert matches_opening(source.copy(), source)
    assert not matches_opening(Image.new('RGB', source.size, 'black'), source)
    assert not matches_opening(source.crop((0, 30, 80, 160)).resize(source.size), source)
    bars = source.copy()
    ImageDraw.Draw(bars).rectangle((0, 0, 79, 8), fill='white')
    assert not matches_opening(bars, source)
    landscape = Image.new('RGB', (160, 80), 'black')
    landscape.paste(source.resize((40, 80)), (60, 0))
    assert matches_opening(landscape, source)
    assert not matches_opening(source.resize((160, 80)), source)
