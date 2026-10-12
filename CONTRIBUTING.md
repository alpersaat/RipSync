# 🤝 RipSync Katkı Sağlama Rehberi (Contributing Guide)

RipSync'e katkıda bulunmak istediğiniz için teşekkürler! RipSync, açık kaynaklı, modern ve yüksek hızlı bir indirme yöneticisidir.

---

## 🛠️ Yerel Geliştirme Ortamı Kurulumu

### 1. Depoyu Klonlayın
```bash
git clone https://github.com/alpersaat/RipSync.git
cd RipSync
```

### 2. Sanal Ortam Oluşturun ve Bağımlılıkları Yükleyin
```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# veya Komut İstemi:
.venv\Scripts\activate.bat

pip install --upgrade pip
pip install -r requirements-dev.txt
```

### 3. Uygulamayı Başlatın
```bash
python main.py
```

### 4. Testleri Çalıştırın
```bash
pytest tests/ -v
```

---

## 📦 Kurulum Paketi (Installer & Standalone EXE) Derleme

Kurulum paketi (`RipSync-Setup.exe`) ve taşınabilir zip (`RipSync-Portable.zip`) oluşturmak için:

1. [Inno Setup 6](https://jrsoftware.org/isinfo.php) sisteminizde kurulu olmalıdır.
2. Komut satırında çalıştırın:
```bash
python build_exe.py
# veya Windows'ta çift tıklayarak:
scripts\build.bat
```
Çıktılar `dist/` klasöründe oluşacaktır:
- `dist/RipSync-Setup.exe` (Windows Kurulum Sihirbazı)
- `dist/RipSync-Portable.zip` (Taşınabilir Sürüm)

---

## 🚀 Katkı Süreci

1. Yeni bir branch açın (`git checkout -b feature/harika-ozellik`).
2. Değişikliklerinizi yapın ve testlerin geçtiğinden emin olun (`pytest`).
3. Temiz ve anlaşılır commit mesajları ile commit'leyin (`git commit -m "feat: yeni özellik eklendi"`).
4. Branch'inizi push edin (`git push origin feature/harika-ozellik`).
5. GitHub üzerinden bir Pull Request (PR) açın.

