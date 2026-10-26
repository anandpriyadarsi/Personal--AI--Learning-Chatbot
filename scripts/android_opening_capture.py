"""Capture an authentic Android cold-launch display, never a View-only raster."""
from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image, ImageChops, ImageOps, ImageStat


def matches_opening(frame: Image.Image, source: Image.Image) -> bool:
    """Require the full fitted artwork, including border arcs and black bars."""
    frame = frame.convert('RGB')
    expected = Image.new('RGB', frame.size, 'black')
    fitted = ImageOps.contain(source.convert('RGB'), frame.size, Image.Resampling.BILINEAR)
    expected.paste(fitted, ((frame.width-fitted.width)//2, (frame.height-fitted.height)//2))
    # Tiles prevent a mostly black system splash, status icons or a clipped
    # tagline from passing merely because most of the approved image is black.
    diff = ImageChops.difference(frame.resize((160,320)), expected.resize((160,320)))
    if max(ImageStat.Stat(diff).mean) > 4:
        return False
    return all(max(ImageStat.Stat(diff.crop((x,y,x+20,y+20))).mean) <= 14
               for y in range(0,320,20) for x in range(0,160,20))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output = root / 'android-evidence/android-opening-launch.png'
    original = Image.open(root / 'android/app/src/main/res/drawable-nodpi/anvaya_opening.jpg')
    package = 'in.anvaya.privateapp'
    subprocess.run(['adb','shell','am','force-stop',package], check=True, capture_output=True)
    launch = subprocess.Popen(['adb','shell','am','start','-n',package+'/.MainActivity'],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            capture = subprocess.run(['adb','exec-out','screencap','-p'], capture_output=True, timeout=10)
            if capture.returncode == 0:
                try:
                    with Image.open(io.BytesIO(capture.stdout)) as frame:
                        if matches_opening(frame, original):
                            output.parent.mkdir(exist_ok=True)
                            output.write_bytes(capture.stdout)  # Actual compositor bytes.
                            print('PASS: complete approved opening visible in actual emulator display')
                            return 0
                except (OSError, ValueError):
                    pass  # A not-yet-ready display is not evidence.
            time.sleep(0.05)
        raise RuntimeError('Approved full opening was not captured on the emulator display')
    finally:
        launch.communicate(timeout=15)
        subprocess.run(['adb','shell','am','force-stop',package], check=True, capture_output=True)


if __name__ == '__main__':
    sys.exit(main())
