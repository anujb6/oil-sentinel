import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from restore_snapshot import image_paths, main


def live(scenes):
    return {'schema_version': 1, 'snapshot_mode': 'live', 'satellite': {'scenes': scenes}}


def test_lists_only_safe_image_paths():
    snap = live([{'image': 'images/cushing-2026-11-09.png'}, {'image': None},
                 {'image': '../../etc/passwd'}, {'image': 'images/other.png'}])
    assert image_paths(snap) == ['images/cushing-2026-11-09.png']


def test_rejects_demo_and_wrong_schema():
    with pytest.raises(ValueError):
        image_paths({'schema_version': 1, 'snapshot_mode': 'demo'})
    with pytest.raises(ValueError):
        image_paths({'schema_version': 2, 'snapshot_mode': 'live'})


def test_main_exit_codes(tmp_path, capsys):
    good = tmp_path / 'good.json'
    good.write_text('{"schema_version":1,"snapshot_mode":"live","satellite":{"scenes":[{"image":"images/cushing-2026-11-04.png"}]}}')
    assert main(str(good)) == 0
    assert capsys.readouterr().out.strip() == 'images/cushing-2026-11-04.png'
    bad = tmp_path / 'bad.json'
    bad.write_text('not json')
    assert main(str(bad)) == 1
