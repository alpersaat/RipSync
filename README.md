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
     - **TikTok:** TikWM API & Aweme motoru ile 0.2 saniyede filigransız doğrudan CDN bağlantısını (`play` / `hdplay`) ve orijinal ses/müzik parçasını (`music` MP3) çözer. TikWM API hizmet dışı olduğunda veya erişilemediğinde kullanıcıya net bir bildirim vererek otomatik olarak `yt-dlp` filigransız yedek motoruna geçer (Graceful Fallback).
     - **Instagram Reels:** `parth-dl` kütüphanesi (GraphQL/Polaris motoru) ile oturum açma veya şifre gerektirmeden herkese açık Reels videolarını doğrudan CDN üzerinden MP4 olarak indirir. Çözümleme aksarsa otomatik olarak `yt-dlp` motoruna geçiş yapılır.
     - **Kullanıcı Dostu Hata Rehberi & Manuel Link Girişi:** YouTube, TikTok, Instagram veya X platformları sayfa yapısını değiştirdiğinde teknik hata kodları yerine Türkçe anlaşılır açıklamalar sunulur ve doğrudan video akış bağlantısını tek tıkla girmeyi sağlayan *"🔗 Manuel Link Gir / Yenile"* penceresi açılır.
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

10. **🔍 Canlı Arama ve Hızlı Filtre Çubuğu (Live Search & Filter Bar):**
    - **Anlık Canlı Arama:** `Ctrl+F` kısayolu veya üst arama kutusu ile dosya adı veya URL'ye göre milisaniyelik gecikmesiz canlı filtreleme. `Esc` tuşu ile tek tuşla temizleme.
    - **Hızlı Durum Filtre Rozetleri:** *Tümü*, *⏳ İnenler*, *✔ Tamamlananlar*, *⏸ Duraklatılanlar*, *❌ Hatalar* butonlarıyla tek tıkla listeyi durumuna göre süzme.

11. **📋 Toplu Bağlantı İndirici & İçe / Dışa Aktarma (Batch URL Add & Import/Export):**
    - **Toplu Link Ekleme (Ctrl+B):** Birden fazla web bağlantısını alt alta yapıştırıp tek tıkla sıralı indirme kuyruğuna ekleme.
    - **Dosyadan İçe Aktarma:** `.txt`, `.m3u` veya `.list` dosyalarından bağlantı listelerini içeri aktarma.
    - **Dışa Aktarma (Export):** İndirme listesini veya seçilen indirmeleri `.txt` ya da `.json` formatında dışa aktarma.

12. **🛡️ Dosya Bütünlüğü Doğrulayıcı (Checksum / Hash Calculator):**
    - **Çoklu Hash Hesaplama:** Tamamlanan herhangi bir dosyaya sağ tıklanarak **MD5**, **SHA-1** ve **SHA-256** hash değerlerini arka planda yüksek hızda hesaplama.
    - **Tek Tıkla Doğrulama:** Web sitesinden alınan beklenen hash değerini yapıştırarak dosyanın bozulup bozulmadığını veya değiştirilip değiştirilmediğini anında doğrulama (*✅ Hash Doğrulandı* / *❌ Uyuşmuyor*).

13. **🔄 Otomatik Ağ Yeniden Deneme (Auto-Retry on Network Drops):**
    - **Kesintilere Karşı Dayanıklılık:** Wi-Fi koptuğunda veya sunucu geçici ağ hatası verdiğinde indirme hemen hata verip durmaz; arka planda üstel bekleme ile otomatik olarak N defa (varsayılan 3 kez) kaldığı yerden devam etmeyi dener.
    - **Yapılandırılabilir Ayarlar:** Ayarlar penceresinden otomatik yeniden deneme açılıp kapatılabilir, maksimum deneme sayısı belirlenebilir.

14. **ℹ️ İndirme Özellikleri & Bağlantı Detayı Penceresi (Download Properties):**
    - Sağ tık menüsünden *"ℹ️ İndirme Özellikleri"* seçilerek dosyanın kaynak URL'si, Referer adresi, kayıt konumu, parçalı indirme (Range) desteği, kanal sayısı, eklenme tarihi, anlık/ortalama hız ve kalan süre gibi teknik detaylarını görüntüleme ve kopyalama.

15. **𝕏 X (Twitter) Doğrudan HD Video İndirici:**
    - Bir Twitter / X tweet video bağlantısı kopyalandığında sağ alttaki bildirim balonu otomatik olarak algılar ve tek tıkla en yüksek kalitede MP4 olarak indirmeyi başlatır.

16. **📈 Canlı Ağ Hız Geçmişi Grafiği (Real-Time Bandwidth Sparkline Graph):**
    - Alt durum çubuğunda son 40 saniyelik indirme hızı dalgalanmasını ve tepe (peak) hızını pürüzsüz degrade dalga formuyla canlı görselleştiren şık mini grafik.

17. **📋 Gelişmiş Kuyruk Önceliği & Sıralama Kontrolleri (Queue Priority & Reordering):**
    - **Esnek Sıralama:** İndirme tablosunda sağ tıklayarak veya `Ctrl+Yukarı` / `Ctrl+Aşağı` kısayollarıyla indirme görevlerini kuyrukta yukarı, aşağı, en başa (öncelikli başlat) veya en sona taşıma.
    - **Otomatik Kapasite Yönetimi:** Sıralama değiştiğinde eşzamanlı indirme limitine göre en üstteki indirme anında devreye alınır.

18. **🎯 Sürükle-Bırak Entegrasyonu (Drag & Drop Dropzone & Export Drop):**
    - **Pencereye Bırakma:** Tarayıcıdan bir bağlantıyı veya masaüstünden `.txt`, `.json`, `.m3u` dosyasını doğrudan RipSync penceresine sürükleyip bırakarak indirmeyi anında başlatma.
    - **Dışa Aktarma (Export Drop):** Tamamlanan dosyaları RipSync tablosundan tutup doğrudan Discord, Slack, masaüstü veya dosya gezgini klasörlerine sürükleyerek kopyalayabilme (`QDrag`).

19. **🏁 Bittiğinde Otomatik Açma / Çalıştırma (Auto-Open on Completion):**
    - Yeni İndirme penceresinde, İlerleme detayında veya sağ tık menüsünde *"🏁 İndirme Tamamlandığında Dosyayı Otomatik Aç"* seçeneği.
    - Büyük kurulum dosyaları (`.exe`, `.iso`) veya filmler biter bitmez kullanıcı başında beklemeden otomatik başlatılır.

20. **🔔 IDM Tarzı Sesli Bildirimler (Audio Notifications):**
    - İndirme tamamlandığında veya ağ hatası oluştuğunda hafif ve şık Windows yerel sistem ses efekti (`winsound.MessageBeep`) ile kullanıcıyı sesli bilgilendirme. Ayarlar menüsünden tek tıkla açılıp kapatılabilir.

21. **💾 Disk Boş Alan Denetimi & Yetersiz Alan Koruması:**
    - **Canlı Durum Göstergesi:** Alt durum çubuğunda indirme sürücüsündeki kullanılabilir boş alanı (`💾 C: 142 GB Boş`) canlı gösterir.
    - **Yetersiz Alan Koruması:** İndirme başlamadan önce diskte kalan boş alan kontrol edilir; yetersiz alan durumunda indirme diski doldurup sistemi kilitlemeden önce kullanıcı uyarılır.

22. **🔢 Sütun Başlıklarına Tıklayarak Akıllı Sayısal Sıralama (Smart Column Sort):**
    - Tablo sütun başlıklarına (*Dosya Adı*, *Boyut*, *Hız*, *Kalan Süre*, *Eklenme Tarihi*) tıklayarak Artan/Azalan akıllı sıralama.
    - Boyut ve hız değerleri salt metin değil, arka plandaki ham byte ve saniye değerlerine göre matematiksel olarak doğru sıralanır.

23. **📊 Detaylı İndirme İstatistikleri & Trafik Paneli (Statistics Dashboard):**
    - Üst araç çubuğundaki *"📊 İstatistikler"* butonu veya alt durum çubuğundaki canlı hız grafiğine tıklanarak açılan şık raporlama paneli.
    - Tüm zamanların toplam indirilen veri trafiği, tamamlanan dosya sayıları, bugünkü trafik hacmi, dosya kategorileri dağılımı ve disk doluluk yüzdesini kartlar ve grafik barlarla görselleştirme.

24. **🔄 Süresi Dolan Bağlantı Adresini Yenileme (Refresh / Update Expired URL):**
    - Google Drive, Rapidgator veya geçici token ile çalışan dosya sunucularında indirme bağlantısı zaman aşımına uğradığında (HTTP 403/410/Link Expired), tüm indirmeyi baştan başlatmak yerine sağ tıklayıp *"🔄 Bağlantı Adresini Yenile"* seçeneğiyle yeni link verilir. RipSync yeni linkin başlıklarını doğrular ve indirmeye tam kaldığı byte'tan devam eder.

25. **🧹 Kayıp / Taşınmış Dosyaları Denetleme ve Ayıklama (Missing Files Cleaner):**
    - Diskte silinmiş, taşınmış veya harici disk çıkarıldığı için ulaşılamayan tamamlanmış dosyalar indirme listesinde *"⚠️ Dosya Eksik"* rozeti ile otomatik işaretlenir. Araç çubuğundaki *"🧹 Eksik Dosyaları Temizle"* butonu veya sağ tık menüsü ile tek tıkla liste geçmişi temizlenebilir.

26. **🌐 Proxy Desteği (HTTP / HTTPS / SOCKS5) ve Kimlik Doğrulama:**
    - Modern Ayarlar panelinden (Ağ & Proxy) HTTP, HTTPS ve SOCKS5 proxy sunucu adresi ve portu tanımlayabilme. Kullanıcı adı ve şifre ile kimlik doğrulama (Authentication) desteği. Hem çok parçalı segment indirmelerinde (`httpx`) hem de sosyal medya/video indirmelerinde (`yt-dlp`) kesintisiz proxy tünellemesi.

27. **⚡ Akıllı Hız Limiti Zamanlaması (Gündüz Sınırla / Gece Tam Hız):**
    - Zamanlayıcı penceresinden günün belirli saatlerinde (örneğin çalışma saatleri 09:00 - 18:00 arasında) bant genişliğini sömürmemek için hız limiti (örn. 2 MB/s) tanımlama, zaman aralığı dışında ise otomatik olarak tam hıza geçme desteği.

28. **📦 Bittiğinde Otomatik Arşiv Çıkarma (.zip, .tar, .gz, .bz2):**
    - Arşiv dosyaları (`.zip`, `.tar`, `.tar.gz`, `.tar.bz2`) indirildiğinde isteğe bağlı olarak otomatik veya sağ tıklanarak *"📦 Arşivi Buraya Çıkart"* ile klasöre açma. Güvenlik korumalı (ZipSlip / Path-traversal engeli) asenkron arka plan motoru.

29. **🎨 Aydınlık / Koyu Tema Desteği & Vurgu Rengi Seçici (Accent Color):**
    - Ayarlar panelinden Koyu (Tokyo Night) ve Aydınlık (Clean Light) tema modları arasında geçiş yapabilme. Mavi, Mor, Zümrüt Yeşili ve Canlı Turuncu olmak üzere 4 farklı vurgu rengi ile kişiselleştirme. Uygulama yeniden başlatılmadan anında canlı uygulanır.

30. **🎯 Çok Kriterli Gelişmiş Filtreleme (Boyut & Tarihe Göre Süzme):**
    - Arama çubuğuna entegre boyut filtresi (`<50 MB`, `50-500 MB`, `500 MB-2 GB`, `>2 GB`) ve eklenme tarihi filtresi (`Bugün`, `Dün`, `Son 7 Gün`, `Daha Eski`) ile yüzlerce indirme arasından aranan dosyaları anında filtreleme.

31. **🏷️ Akıllı Dosya Çakışma Yönetimi & Otomatik Adlandırma (Conflict & Auto-Rename):**
    - İndirilen dosya kayıt klasöründe zaten mevcutsa üzerine yazıp veriyi kaybetmeyi önler; Ayarlar panelinden *"Otomatik Numaralandır (`dosya (1).ext`)"*, *"Üzerine Yaz"* veya *"İndirmeyi Atla"* tercihleri belirlenebilir.
    - URL sonundaki gereksiz sorgu parametrelerini ayıklar, Windows'un yasaklı karakterlerini (`<>:"/\|?*`) ve ayrılmış aygıt adlarını (`CON`, `PRN`, `AUX`, `NUL`) güvenle temizler.
    - Yeni İndirme penceresinde dosya çakışması anlık olarak sarı uyarı kartıyla canlı gösterilir.

32. **⚖️ Görev Başına Bant Genişliği Önceliği & Dinamik Paylaşım (Bandwidth Priority Weighting):**
    - Çoklu indirmelerde acil dosyaların diğerlerinden daha hızlı inmesi için **🚀 Yüksek Öncelik (3.0x - %70 Hız Payı)**, **⚖️ Normal Öncelik (1.0x - Dengeli)** veya **🐢 Düşük Öncelik (0.33x - Arka Plan)** atayabilme.
    - İndirme tablosundan sağ tıklanarak, toplu seçim menüsünden veya Yeni İndirme / Toplu Link Ekleme pencerelerinden doğrudan öncelik belirleme.
    - Global hız sınırı aktifken toplam bant genişliğini görevlerin öncelik ağırlıklarına göre matematiksel olarak paylaştırır; tabloda ve özellikler penceresinde rozetlerle canlı görselleştirilir.

33. **🤖 İndirme Bittiğinde Özel Komut & Webhook Bildirimleri (Post-Download Automation & Webhooks):**
    - **Özel Komut Çalıştırma (CLI / Script):** İndirme tamamlandığında arka planda kullanıcı tanımlı komut veya betik çalıştırma. `{filepath}`, `{filename}`, `{filesize}`, `{category}`, `{url}`, `{status}` gibi şablon değişkenleriyle scriptlere dinamik parametre aktarımı.
    - **Webhook Entegrasyonu (Discord / Slack / REST API):** İndirme bittiğinde Discord sunucunuza, Slack kanalınıza veya özel webhook servisinize görsel kartlı (embed) anlık JSON bildirimi gönderme.
    - **Gizlilik Koruması & Güvenlik:** Kişisel klasör yapısı ve yerel kullanıcı adının dışarı sızmasını önlemek amacıyla yerel dosya yolu `{filepath}` varsayılan olarak gönderilmez; yalnızca kullanıcının açık onayıyla isteğe bağlı dahil edilir. Arayüzde açık veri gizliliği uyarısı yer alır.
    - **Canlı Test Butonu:** Ayarlar -> *Otomasyon & Webhook* sekmesinden tek tıkla webhook bağlantısını anında test edip doğrulama.

34. **🌙 Akıllı Sistem Uykusunu Engelleme (Keep-Awake / Sleep Prevention):**
    - **Kesintisiz Gece İndirmeleri:** Büyük dosyalar veya oynatma listeleri indirilirken Windows'un uyku veya bekleme moduna (Sleep/Standby) geçmesini otomatik olarak engeller (`SetThreadExecutionState` Win32 API).
    - **Otomatik Güç Dönüşü:** Kuyruk bittiğinde veya tüm indirmeler tamamlandığında güç kilitlerini serbest bırakarak sistemin varsayılan güç planına dönmesini sağlar.
    - **Yapılandırılabilir Tercih:** Ayarlar -> Hız & Güç sekmesinden tek tıkla etkinleştirilip devre dışı bırakılabilir.

35. **📑 Ardışık Bağlantı Kalıp Sihirbazı (Pattern / Sequential Batch URL Generator - IDM Tarzı):**
    - **Gömülü Aralıklar:** `https://site.com/file_[01-20].zip`, `image_[1-100:5].jpg` veya `part_[a-z].rar` gibi şablonlardan tek tıkla onlarca bağlantıyı otomatik üretme.
    - **Yer Tutucu & Canlı Önizleme:** Toplu İndirme Penceresindeki (`Ctrl+B`) *"🪄 Kalıp Sihirbazı"* ile basamak dolgusu (01, 001) ve canlı önizleme eşliğinde bağlantıları kuyruğa aktarma.

36. **🍪 Tarayıcı Çerezlerini İçe Aktarma (Browser Cookies Importer - YouTube / Instagram):**
    - **Korumalı İçerik Desteği:** Google Chrome, Microsoft Edge, Brave veya Mozilla Firefox oturum çerezlerini entegre ederek YouTube'daki yaş kısıtlamalı (+18) videoları, üyelere özel içerikleri ve oturum gerektiren Instagram gönderilerini sorunsuz indirme.
    - **Esnek Seçim:** Ayarlar panelinden tarayıcı profili belirleme veya devre dışı bırakma.

37. **📝 YouTube & Video Altyazı (.SRT) ve Kapak Resmi İndirici (Subtitles & Thumbnail Extractor):**
    - **Otomatik Altyazı Kaydetme:** Video indirilirken Türkçe, İngilizce veya orijinal dildeki altyazıları doğrudan `.srt` / `.vtt` olarak dosyanın yanına kaydetme seçeneği.
    - **HD Kapak Görseli:** Yeni İndirme penceresinden video kapağını (`.jpg`) tek tıkla arşivleme imkanı.

38. **🎵 Akıllı MP3 Etiket Düzenleyici & Albüm Kapağı Gömücü (ID3 Tag & Artwork Injector):**
    - **Müzik Çalar Entegrasyonu:** Sosyal medyadan veya YouTube'dan `"Sadece Ses / Müzik (MP3)"` indirildiğinde sanatçı adını, şarkı başlığını ve albüm kapağını doğrudan MP3 dosyasının içine (ID3v2 metadata) gömer.
    - Otomobil teyplerinde, iPhone/Android telefonlarda ve müzik çalarlarda eksiksiz parça bilgisi ve kapak görseli sağlar.

39. **🏷️ İndirmeler İçin Özel Renkli Etiketler & Filtreleme (Tags System):**
    - **Kişisel Gruplandırma:** Dosyalara `İş`, `Ders`, `Acil`, `Arşiv` gibi özel etiketler atayabilme.
    - **Renkli Rozetler & Canlı Filtre:** İndirme tablosunda dosya adının yanında etiket rozetleri (`[İş]`, `[Ders]`), sol panelde *"🏷️ Etiketler"* ağacı ve sağ tık menüsünden tek tıkla toplu etiket atama.

40. **🌐 Alan Adına (Siteye) Özel İndirme Kuralları (Site Rules & Per-Domain Folders):**
    - **Otomatik Klasör Yönlendirmesi:** Belirli web siteleri için özel kayıt klasörleri tanımlayabilme (Örn: `github.com` ➔ `C:\Projeler`, `artstation.com` ➔ `D:\Görseller`).
    - **Akıllı Eşleşme:** URL girildiğinde (Yeni İndirme, Tarayıcı Eklentisi veya Toplu Ekleme) domain kuralı anında devreye girer ve hedef klasör otomatik belirlenir. Ayarlar -> *Site Kuralları* sekmesinden kolay kural yönetimi.

41. **🛡️ Akıllı Yinelenen (Duplicate) İndirme Koruması:**
    - **Mükerrer İndirme Engeli:** Daha önce indirilmiş veya listede mevcut olan bir URL ya da dosya yeniden indirilmek istendiğinde kullanıcıyı uyarır.
    - **Akıllı Eylemler:** Açılan diyalog üzerinden tek tıkla *"📂 Dosyayı / Klasörü Aç"*, *"🔄 Yeniden İndir"* veya *"❌ İptal Et"* seçenekleri. Ayarlar -> Genel sekmesinden açılıp kapatılabilir.

42. **🎯 Pano (Clipboard) Akıllı Filtreleme & Kara Liste:**
    - **Hedef Odaklı Pano İzleme:** Sadece video, ses ve dosya indirmelerini yakalamak için *"🎯 Yalnızca doğrudan medya ve dosya uzantılarını yakala"* seçeneği.
    - **Özel Kara Liste (Exclusion Domains):** `google.com`, `github.com`, `stackoverflow.com` gibi istenmeyen web sitelerini kara listeye ekleyerek rahatsız edici bildirimleri engelleme.

43. **🗂️ Bağımsız Çoklu Kuyruk Yönetimi (Custom Download Queues):**
    - **Kişiselleştirilmiş Kuyruklar:** *"Ana Kuyruk"*, *"İş Dosyaları"*, *"Dizi/Film Arşivi"* gibi sınırsız sayıda bağımsız indirme kuyruğu oluşturabilme.
    - **Kuyruk Odaklı Kontrol:** Sol paneldeki ağaç menüsünden kuyrukları filtreleme, sağ tıklayarak seçilen kuyruğu tek tıkla başlatma/duraklatma ve indirme görevlerini kuyruklar arasında kolayca taşıma.

44. **📶 Tarifeli Bağlantı (Hotspot / Mobil Veri) Koruması (Metered Connection Guard):**
    - **Mobil Kota Tasarrufu:** Telefonunuzun internetine (Hotspot / Taşınabilir Erişim Noktası) veya tarifeli bir ağa bağlandığınızda büyük indirmeleri otomatik beklemeye alarak internet paketinizin tükenmesini önler.
    - **Tek Tıkla Geçici İzin:** Durum çubuğundaki *"📶 Tarifeli Bağlantı (Kota Koruması Aktif)"* rozetine tıklayarak acil durumlarda kota korumasını tek tıkla geçici olarak aşabilme.

---

## 🌐 Chrome / Edge / Brave Eklentisi Kurulumu (1 Dakika)

Tarayıcınız ile masaüstü uygulamasını entegre etmek için:

1. **Google Chrome**, **Brave** veya **Microsoft Edge** tarayıcınızı açın.
2. Adres satırına `chrome://extensions` (Edge için `edge://extensions`) yazıp Enter'a basın.
3. Sağ üst köşedeki **"Geliştirici modu" (Developer mode)** anahtarını açın.
4. Sol üstte beliren **"Paketlenmemiş öğe yükle" (Load unpacked)** düğmesine tıklayın.
5. RipSync kurulum dizinindeki veya proje içerisindeki **`extension`** klasörünü seçin.
6. Eklenti anında kurulacaktır. Eklenti simgesine tıkladığınızda **"🟢 Masaüstü Uygulaması Bağlı"** durumunu göreceksiniz.

> Not: `extension/config.json` repoda yoktur; masaüstü uygulaması ilk çalıştırmada köprü portunu ve güvenli token'ı bu dosyaya kendisi yazar (örnek için `extension/config.json.example`).

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
