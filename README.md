# ⚡ RipSync - Modern Internet Download Manager (IDM) Alternatifi

[![GitHub Release](https://img.shields.io/github/v/release/alpersaat/RipSync?style=flat-square&color=blue)](https://github.com/alpersaat/RipSync/releases)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue?style=flat-square&logo=windows)](../../releases)
[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-brightgreen?style=flat-square&logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

Açık kaynaklı, modern, yüksek hızlı, 32 kanala kadar dinamik parçalı indirme yöneticisi ve Google Chrome / Chromium tabanlı tarayıcı uzantısı.

---

## 📥 İndir ve Kur (Doğrudan Setup)

Herhangi bir Python kurulumuna ihtiyaç duymadan doğrudan kurup kullanabilirsiniz:

| İndirme Paketi | Format | Açıklama | Bağlantı |
| :--- | :--- | :--- | :--- |
| **Windows Kurulum Paketi (Önerilen)** | `.exe` (Setup Sihirbazı) | Başlat menüsü, masaüstü kısayolu ve Windows başlangıç entegrasyonu | [**📥 RipSync-Setup.exe İndir**](../../releases/latest) |
| **Taşınabilir Sürüm (Portable)** | `.zip` (Arşiv) | Kurulum gerektirmeden istediğiniz klasörden veya USB bellekten çalıştırın | [**📦 RipSync-Portable.zip İndir**](../../releases/latest) |

> 💡 **Not:** En son kararlı sürümü GitHub sayfasındaki sağ tarafta yer alan **[Releases (Sürümler)](../../releases)** sekmesinden indirebilirsiniz.

---

## 🌟 Özellikler

1. **Instagram Reels & TikTok Filigransız (Watermark-Free) Video İndirici:**
   - **%100 Filigransız (Clean HD) Video Desteği:** TikTok videoları ve Instagram Reels / Gönderi videolarındaki logolar, kullanıcı adı filigranları ve platform etiketleri olmadan doğrudan orijinal yüksek çözünürlüklü (HD MP4) akışı indirir.
   - **Gelişmiş Çift Katmanlı Çözümleyici Motor (`SocialResolver`):**
     - **TikTok:** TikWM API & Aweme motoru ile 0.2 saniyede filigransız doğrudan CDN bağlantısını (`play` / `hdplay`) ve orijinal ses/müzik parçasını (`music` MP3) çözer. `yt-dlp` tarafında da `curl_cffi` tarayıcı parmak izi taklidi (impersonation) ve filigranlı formatları kesin olarak eleyen akıllı filtreleme devrededir.
     - **Instagram Reels:** Logged-out Polaris GraphQL ve anonim medya motoru sayesinde oturum açma veya hesap şifresi gerektirmeden herkese açık Reels videolarını doğrudan Facebook/Instagram CDN'i üzerinden en yüksek hızda ve sesle birlikte MP4 olarak indirir.
   - **Pano Takibi (Clipboard) Otomatik Algılama:** Bir TikTok (kısa linkler `vt.tiktok.com`, `vm.tiktok.com` dahil) veya Instagram Reels bağlantısı kopyalandığında (Ctrl+C), sağ alt köşede *"✨ TikTok (Filigransız)"* veya *"✨ Instagram Reels (Filigransız)"* bildirim kartı belirir ve tek tıkla filigransız indirmeyi başlatır.
   - **Yeni İndirme Penceresinde Özel Bildirim:** Bağlantı girildiğinde *"✨ Instagram Reels / TikTok Algılandı: Filigransız Video İndirme Aktif!"* rozeti gösterilir ve dosya kategorisi otomatik olarak Videolar'a yönlendirilir.
   - **Chrome Eklentisi Kayan Buton Uyarlaması:** TikTok ve Instagram sayfalarında gezinirken video oynatıcısının üzerinde doğrudan *"✨ Filigransız İndir"* butonu ve açılır menüde *"✨ Filigransız Video İndir (HD MP4)"* ile *"🎵 Sadece Ses / Müzik (MP3)"* seçenekleri sunulur.

2. **YouTube Oynatma Listesi (Playlist) Toplu İndirici:**
   - **Tüm Videoları Otomatik Tarama:** Verilen YouTube çalma listesi bağlantısındaki (veya playlist parametresi içeren video linkindeki) tüm videoları `yt-dlp` üzerinden saniyeler içinde tarar, başlıklarını, sürelerini, video kapak resimlerini ve toplam video sayısını listeler.
   - **Esnek Video Seçimi:** Çalma listesindeki videolardan sadece istediklerinizi onay kutularıyla seçebilme, *"Tümünü Seç"*, *"Tümünü Kaldır"*, *"Seçimi Tersine Çevir"* butonları ve başlığa göre anlık canlı arama/filtreleme.
   - **Kalite & Format Tercihi:** Tüm seçilen videoları tek tıkla en yüksek kalitede (4K / 1080p MP4), 720p/480p veya **"Sadece Müzik / Ses (MP3)"** olarak indirme imkanı.
   - **Otomatik Sıralama Numaralandırması:** Dosya adlarının başına `01 - `, `02 - ` gibi sıra numarası ekleyerek müzik/video arşivinizde çalma listesi sırasının korunmasını sağlar.
   - **Tek Tıkla Sırayla İndirme:** Seçilen videoları tek tıkla indirme kuyruğuna aktarır; belirlediğiniz sıralı eşzamanlı indirme limitine göre (`max_concurrent`) videolar sırayla birbiri ardına otomatik olarak indirilir.
   - **Pano Takibi & Üst Araç Çubuğu Entegrasyonu:** Bir YouTube çalma listesi kopyalandığında sağ alttaki bildirim balonu listeyi hemen algılar ve tek tıkla toplu indirme penceresini açar. Ana araç çubuğunda ve sistem tepsisinde de doğrudan *"📑 Oynatma Listesi İndir"* düğmesi yer alır.

3. **Çok Kanallı Dinamik Parçalama (Segmented Download Engine):**
   - Tek bir dosyayı eşzamanlı olarak 8, 16 veya 32 HTTP `Range` bağlantısıyla parçalara bölerek sunucu hız limitlerini aşar ve bant genişliğini maksimuma çıkarır.
   - **Dinamik Parça Bölme:** Erken biten iş parçacıkları yavaş kalan diğer parçaları otomatik olarak 2'ye bölüp yardıma gelerek indirmeyi en üst hızda tutar.
   - **Duraklat & Devam Et (Pause & Resume):** Kesintiye uğrayan indirmeleri baştan başlamadan kaldığı byte'tan devam ettirir.
   - **Doğrudan Ofset Yazımı:** Parçalar doğrudan hedef dosya ofsetine yazılır; indirme bittiğinde dosyayı birleştirmek için dakikalarca bekleme yapmaz.

4. **Otomatik Akıllı Kategorizasyon (Klasörleme):**
   - İndirilen dosyaların uzantılarına göre otomatik olarak ilgili Windows alt klasörlerine yönlendirilmesi ve kaydedilmesi:
     - `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm` ➔ **İndirilenler / Videolar**
     - `.mp3`, `.wav`, `.flac`, `.aac`, `.m4a` ➔ **İndirilenler / Müzik**
     - `.zip`, `.rar`, `.7z`, `.tar`, `.gz` ➔ **İndirilenler / Arşivler**
     - `.exe`, `.msi`, `.iso`, `.bat`, `.apk` ➔ **İndirilenler / Programlar**
     - `.pdf`, `.docx`, `.doc`, `.xlsx`, `.pptx`, `.txt` ➔ **İndirilenler / Belgeler**
   - İlgili klasörler diskte henüz yoksa otomatik oluşturulur. İndirme penceresinde dosya adı girildikçe veya link çözümlendikçe hedef klasör anlık olarak otomatik eşlenir. İstenirse *Ayarlar* menüsünden açılıp kapatılabilir.

5. **Gelişmiş Hız Sınırlayıcı (Speed Limiter) & Bant Genişliği Kontrolü (IDM Tarzı):**
   - Oyun oynarken, yayın yaparken veya film izlerken internetinizin tıkanmaması için esnek bant genişliği kontrolü.
   - **Ana Araç Çubuğunda Canlı Kaydırıcı (Slider):** Üst araç çubuğundaki kaydırıcı ile 256 KB/s'den 50 MB/s'ye kadar hız limitini anında değiştirin.
   - **Tek Tıkla Hız Sınırı Açma / Kapatma (Tam Hız):** IDM'deki gibi tek tıkla hız sınırını devreye alın veya tam hıza geçin.
   - **Hızlı Hazır Limitler (Presets):** 512 KB/s, 1 MB/s, 2 MB/s, 5 MB/s (Önerilen), 10 MB/s, 25 MB/s, 50 MB/s seçenekleri.
   - **İndirme Detay Penceresinde Özel Hız Limiti:** Her indirme penceresinde (`ProgressDialog`) o indirmeye özel bağımsız hız kaydırıcısı ve hazır limitler.
   - **Token Bucket Algoritması:** Ağ paketlerini hassas biçimde zamanlayarak pürüzsüz ve gerçek bant genişliği sınırlaması sağlar.

6. **Zamanlayıcı / İndirme Kuyruğu Planlama (Scheduler & Gece İndirmesi):**
   - **Gece İndirmesi Senaryosu:** “Gece 02:00’de indirmeyi başlat, sabah 07:00’de durdur.”
   - **Otomatik Başlatma ve Durdurma:** Belirlenen başlangıç saatinde indirme kuyruğu otomatik devreye girer; bitiş saatinde ise indirmeler duraklatılır.
   - **Bitiş Sonrası Güç Yönetimi:** Zamanlayıcı durduğunda bilgisayarı açık bırakmamak için *"Tümünü Duraklat ve Bilgisayarı Kapat"* (Shutdown) veya *"Uyku Moduna Al"* (Sleep / Suspend) seçenekleri.
   - **Tekrarlama Günleri:** Her gün (Günlük), Hafta içi, Hafta sonu veya seçilen özel günlere göre otomatik zamanlama.
   - **Tek Tıkla Hızlı Şablonlar:** 🌙 *Gece İndirmesi (02:00 - 07:00)*, ⭐ *Gece Yarısı (00:00 - 06:00)*, 🏢 *Mesai Dışı (19:00 - 08:00)* hazır butonları.

7. **Sıralı İndirme (Sequential Download) & Kuyruk Önceliği:**
   - **Eşzamanlı İndirme Limiti:** Aynı anda kaç dosyanın ineceği (ör. aynı anda en fazla 2 dosya insin, biri bitince diğeri başlasın) doğrudan ana araç çubuğundaki *"⚡ Sıralı: [ 2 ] Dosya"* seçicisinden, Ayarlar menüsünden veya Zamanlayıcı penceresinden ayarlanabilir.
   - **Otomatik Sıradaki Dosyaya Geçiş:** İnen dosyalardan biri tamamlandığında kuyruktaki bir sonraki dosya anında indirilmeye başlar.
   - **Kuyruk Sıralaması & Öncelik Düzenleme:** Dosya tablosunda sağ tık menüsünden indirme sırası kolayca değiştirilebilir.

8. **Sistem Tepsisi (System Tray) & Windows Bildirimleri:**
   - **X Tuşuyla Tepsiye Küçülme:** Pencere kapatıldığında arka planda saatin yanındaki sistem tepsisinde sessizce çalışmayı sürdürür.
   - **Windows Toast Bildirimleri ("Klasörde Göster"):** İndirme bittiğinde yerel Windows 10/11 Toast bildirimi gösterilir ve tek tıkla dosya Gezgin'de vurgulanmış açılır.

9. **Chrome Eklentisi (Manifest V3):**
   - Tarayıcıdaki tüm indirmeleri yakalayarak otomatik olarak uygulamaya yönlendirir.
   - Sayfalardaki video oynatıcılarda kayan **"⚡ Bu Videoyu İndir"** düğmesi (Video Sniffer) gösterir.
   - Bağlantılara sağ tıklayıp *"Bu bağlantıyı RipSync ile indir"* menüsü sunar.

---

## 🌐 Chrome / Edge / Brave Eklentisi Kurulumu (1 Dakika)

Tarayıcınız ile masaüstü uygulamasını entegre etmek için:

1. **Google Chrome**, **Brave** veya **Microsoft Edge** tarayıcınızı açın.
2. Adres satırına `chrome://extensions` (Edge için `edge://extensions`) yazıp Enter'a basın.
3. Sağ üst köşedeki **"Geliştirici modu" (Developer mode)** anahtarını açın.
4. Sol üstte beliren **"Paketlenmemiş öğe yükle" (Load unpacked)** düğmesine tıklayın.
5. RipSync kurulum dizinindeki veya proje içerisindeki **`extension`** klasörünü seçin.
6. Eklenti anında kurulacaktır. Eklenti simgesine tıkladığınızda **"🟢 Masaüstü Uygulaması Bağlı"** durumunu göreceksiniz.

---

## 💻 Geliştiriciler İçin Kaynak Koddan Çalıştırma

Eğer projeyi kaynak kodundan çalıştırmak veya geliştirmek isterseniz:

### 1. Depoyu Klonlama & Bağımlılıklar
```bash
git clone https://github.com/alpersaat/RipSync.git
cd RipSync

# Sanal ortam oluşturma ve etkinleştirme
python -m venv .venv
.venv\Scripts\activate

# Bağımlılıkları yükleme
pip install -r requirements-dev.txt
```

### 2. Uygulamayı Başlatma
```bash
python main.py
```
veya Windows'ta çift tıklayarak:
```cmd
scripts\run.bat
```

### 3. Kendi Kurulum (.exe) ve Taşınabilir (.zip) Paketini Derleme
Sisteminizde [Inno Setup 6](https://jrsoftware.org/isinfo.php) kurulu olduğundan emin olduktan sonra:
```bash
python build_exe.py
# veya Windows'ta çift tıklayarak:
scripts\build.bat
```
Derleme tamamlandığında `dist/` klasöründe:
- `dist/RipSync-Setup.exe`
- `dist/RipSync-Portable.zip`
otomatik olarak hazır olacaktır.

---

## 🤝 Katkıda Bulunma

Katkılarınızı memnuniyetle kabul ediyoruz! Lütfen katkı sağlamadan önce [CONTRIBUTING.md](CONTRIBUTING.md) dosyasını inceleyin.

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) kapsamında açık kaynak olarak lisanslanmıştır.
