import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from update import unpack_eia_dataframe, pressure_signal, fetch_stac, siri_briefing, build


def fake(name, last, diff, date='2026-10-30'):
    return {'name': name, 'as_of': date, 'mb': last, 'week_change_mb': diff}


def test_parse_eia_thousands_to_millions_and_weekly_change():
    frame = pd.DataFrame({'Date': ['2026-10-16','2026-10-23','2026-10-30'], 'data': [27594,26970,27250]})
    actual = unpack_eia_dataframe(frame, 'W_EPC0_SAX_YCUOK_MBBL', 'Cushing')
    assert actual['as_of'] == '2026-10-30'
    assert actual['mb'] == 27.25
    assert actual['week_change_mb'] == .28
    assert len(actual['history']) == 3


def test_eia_filters_invalid_and_sorts():
    frame = pd.DataFrame({'Date': ['bad','2026-10-30','2026-10-23'], 'data': ['bad',10000,11000]})
    result = unpack_eia_dataframe(frame,'TEST','Test')
    assert result['week_change_mb'] == -1


def test_signal_mixed_does_not_fake_confirmation():
    series={'us_crude':fake('US',410,-.865),'cushing':fake('Cushing',27.25,.28)}
    assert pressure_signal(series)['key']=='mixed'


def test_signal_strong_build():
    series={'us_crude':fake('US',410,3.6),'cushing':fake('Cushing',27.25,.85)}
    assert pressure_signal(series)['key']=='loosening'


def test_signal_wrong_period_disallowed():
    series={'us_crude':fake('US',410,3.6),'cushing':fake('Cushing',27.25,.85,date='2026-10-23')}
    assert pressure_signal(series)['key']=='unavailable'


def test_siri_demo_is_explicit():
    demo={'snapshot_mode':'demo','eia':{'series':{'us_crude':fake('US',409.760,-.865),'cushing':fake('Cushing',27.25,.28)},'signal':{'title':'Mixed inventory picture'}},'satellite':{'latest_scene_date':None}}
    txt=siri_briefing(demo)
    assert 'historical sample' in txt
    assert '27.25 million barrels' in txt


class FakeSTACResponse:
    def raise_for_status(self): pass
    def json(self):
        return {'features':[
            {'id':'scene_1','bbox':[-97,35,-96,37],'properties':{'datetime':'2026-11-08T12:00:00Z','eo:cloud_cover':19},'assets':{'visual':{'href':'https://example.com/visual.tif'}},'links':[{'rel':'self','href':'https://example.com/item'}]},
            {'id':'scene_2','bbox':[-97,35,-96,37],'properties':{'datetime':'2026-11-08T09:00:00Z','eo:cloud_cover':45},'assets':{},'links':[]},
            {'id':'bad_geography','bbox':[-30,25,-10,28],'properties':{'datetime':'2026-11-09T12:00:00Z','eo:cloud_cover':0},'assets':{},'links':[]},
        ]}

class FakeSession:
    def get(self, *args, **kwargs): return FakeSTACResponse()


def test_stac_dedupes_scenes_per_day():
    result=fetch_stac(FakeSession(),datetime(2026,11,12,tzinfo=timezone.utc))
    assert len(result['scenes']) == 1
    assert result['scenes'][0]['cloud_percent']==19
    assert result['scenes'][0]['date']=='2026-11-08'


def test_build_does_not_claim_live_eia_when_failed():
    old={'eia':{'series':{'us_crude':fake('US',409.760,-.865),'cushing':fake('Cushing',27.25,.28)}}}
    with patch('update.fetch_eia_series', side_effect=RuntimeError('offline')), patch('update.fetch_stac', side_effect=RuntimeError('offline')), patch('update.try_market_quote',side_effect=RuntimeError('offline')):
        result=build(old,session=FakeSession(),now=datetime(2026,11,12,tzinfo=timezone.utc),render_images=False)
    assert result['snapshot_mode']=='partial'
    assert result['eia']['status']=='stale'
    assert result['eia']['signal']['key']=='unavailable'


def test_satellite_rgb_crop_is_a_real_georeferenced_window(tmp_path, monkeypatch):
    """Exercise the actual raster-to-PNG path with an in-memory synthetic GeoTIFF.

    The synthetic test raster is never shipped as a satellite image.
    """
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import transform
    import numpy as np
    import update
    x, y=transform('EPSG:4326','EPSG:32614',[update.SITE_LON],[update.SITE_LAT])
    path=tmp_path/'test.tif'
    raw=np.zeros((3,800,800),dtype=np.uint8)
    raw[0]=150;raw[1]=103;raw[2]=75
    with rasterio.open(path,'w',driver='GTiff',count=3,width=800,height=800,dtype='uint8',crs='EPSG:32614',transform=from_origin(x[0]-4000,y[0]+4000,10,10)) as dst:
        dst.write(raw)
    monkeypatch.setattr(update,'IMAGES',tmp_path)
    actual_open=rasterio.open
    monkeypatch.setattr(rasterio,'open',lambda *_args,**_kwargs: actual_open(path))
    result=update.save_crop({'date':'2026-10-30','_assets':{'visual':{'href':'https://example.org/test.tif'}}},'local.png')
    assert result
    from PIL import Image
    img=Image.open(tmp_path/'local.png')
    assert img.size==(512,512)
    assert img.getpixel((100,100))==(150,103,75)


class RecordingSession:
    def __init__(self): self.params=None
    def get(self, *args, **kwargs):
        self.params=kwargs.get('params'); return FakeSTACResponse()


def test_stac_sends_rfc3339_datetime_range():
    # Earth Search rejects date-only ranges ("does not match RFC3339 format").
    session=RecordingSession()
    fetch_stac(session,datetime(2026,11,12,tzinfo=timezone.utc))
    assert session.params['datetime']=='2026-09-08T00:00:00Z/2026-11-13T23:59:59Z'
