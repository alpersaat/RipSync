# Manuel testler

Bu klasördeki testler gerçek ağa bağlanır / gerçek tarayıcı (Playwright) gerektirir.
`pytest.ini` içindeki `norecursedirs = manual` sayesinde varsayılan `pytest tests/`
koşusuna dahil edilmezler.

## Çalıştırma

- `test_stream_fix.py` pytest testidir: `python -m pytest tests/manual -v`
- `test_ad_filter.py`, `test_button_position.py`, `test_button_real_sites.py`
  ve `test_idm_engine.py` bağımsız betiktir (`main()` / `if __name__ == "__main__"`).
  Doğrudan çalıştır: `python tests/manual/test_ad_filter.py`

Notlar:
- Chrome kurulu olmalı; ilk kullanımda `playwright install` gerekir.
- Betikler ROOT/EXT_DIR'i proje kökünden hesaplar (taşınmaya uygun yazıldı).
- `test_idm_engine.py` ve `test_stream_fix.py` gerçek ağdan indirme yaptığı için
  bağlantı durumuna göre kırılgandır.
- Qt/offscreen gerekmez.
