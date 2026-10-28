"""A blank system splash or cropped/replaced artwork is not launch evidence."""
import io
import subprocess

import pytest
from PIL import Image, ImageDraw
from scripts import android_opening_capture as capture
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


def capture_device(monkeypatch, tmp_path, *, launch_error=None):
    """Model a cold compositor taking longer than the real opening is visible."""
    script = tmp_path / 'scripts/android_opening_capture.py'
    source = tmp_path / 'android/app/src/main/res/drawable-nodpi/anvaya_opening.jpg'
    source.parent.mkdir(parents=True)
    artwork().save(source)
    with Image.open(source) as approved:
        opening = io.BytesIO()
        approved.save(opening, format='PNG')
    home = io.BytesIO()
    Image.new('RGB', (80, 160), 'white').save(home, format='PNG')
    clock = {'now': 0.0, 'cold': True, 'launch': None}

    def run(command, **kwargs):
        if command == ['adb', 'exec-out', 'screencap', '-p']:
            clock['now'] += 8 if clock['cold'] else .1
            clock['cold'] = False
            elapsed = clock['now'] - clock['launch'] if clock['launch'] is not None else 99
            frame = opening.getvalue() if 0 <= elapsed < 2 else home.getvalue()
            return subprocess.CompletedProcess(command, 0, frame, b'')
        assert command == ['adb', 'shell', 'am', 'force-stop', 'in.anvaya.privateapp']
        return subprocess.CompletedProcess(command, 0, b'', b'')

    class Launch:
        returncode = 1 if launch_error else 0

        def __init__(self, command, **kwargs):
            assert command == ['adb', 'shell', 'am', 'start', '-n',
                               'in.anvaya.privateapp/.MainActivity']
            clock['launch'] = clock['now']

        def poll(self):
            return self.returncode

        def communicate(self, timeout):
            return (launch_error or b'Starting: Intent'), None

    monkeypatch.setattr(capture, '__file__', str(script))
    monkeypatch.setattr(capture.subprocess, 'run', run)
    monkeypatch.setattr(capture.subprocess, 'Popen', Launch)
    monkeypatch.setattr(capture.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(capture.time, 'sleep', lambda delay: clock.update(now=clock['now'] + delay))
    return opening.getvalue(), tmp_path / 'android-evidence/android-opening-launch.png'


def test_cold_capture_is_ready_before_launch_and_saves_actual_matching_frame(monkeypatch, tmp_path):
    expected, output = capture_device(monkeypatch, tmp_path)
    assert capture.main() == 0
    assert output.read_bytes() == expected


def test_failed_activity_start_reports_adb_diagnostic_without_saving_evidence(monkeypatch, tmp_path):
    _, output = capture_device(monkeypatch, tmp_path,
                               launch_error=b'Error: Activity class does not exist')
    with pytest.raises(RuntimeError, match='Activity class does not exist'):
        capture.main()
    assert not output.exists()
