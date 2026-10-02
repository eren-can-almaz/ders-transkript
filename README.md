# Ders Transkript

Ders kayıtlarını ve mikrofon kayıtlarını **internetsiz** metne çeviren masaüstü uygulaması
(Whisper, tamamen bilgisayarınızda çalışır). Arayüz: Türkçe / English / Deutsch.

## İndirme

[**Releases**](../../releases/latest) sayfasından bilgisayarınıza uygun dosyayı indirin.
Modeller dosyanın içindedir: Python, model veya başka bir şey kurmanız gerekmez.

| Bilgisayar | Dosya | Çalıştırma |
|---|---|---|
| Windows 10/11 | `DersTranskript-windows.zip` | Zip'e sağ tık → **Tümünü ayıkla** → klasördeki `DersTranskript.exe` |
| Mac (M1/M2/M3/M4), macOS 14+ | `DersTranskript-mac-apple-silicon.dmg` | DMG'yi açın, uygulamayı **Uygulamalar**'a sürükleyin |
| Mac (Intel), macOS 13+ | `DersTranskript-mac-intel.dmg` | aynı |
| Linux (Ubuntu 22.04+, Debian 12+, Fedora 36+) | `DersTranskript-linux.tar.gz` | Açın, klasörde `./kur.sh` çalıştırın → menüde **Ders Transkript** |

Mac'inizin hangi işlemciye sahip olduğunu  menüsü → **Bu Mac Hakkında** → "Çip" (Apple M…) ya da
"İşlemci" (Intel) satırından görebilirsiniz.

### İlk açılıştaki güvenlik uyarısı

Uygulama ücretli bir geliştirici sertifikasıyla imzalanmadığı için sistem ilk açılışta uyarır.
Bu bir kez yapılır:

- **Windows** ("Windows bilgisayarınızı korudu"): **Ek bilgi** → **Yine de çalıştır**.
- **macOS** ("açılamıyor" / "geliştirici doğrulanamadı"): uygulamaya bir kez açmayı deneyin,
  sonra **Sistem Ayarları → Gizlilik ve Güvenlik** → en altta **Yine de Aç**.
  (macOS 14'te: uygulamaya sağ tık → **Aç** → **Aç**.)
- Mikrofonla canlı kayıt için ilk seferde sorulan **mikrofon izni**ni onaylayın.

## Kullanım

- **+** ile yeni kayıt başlatın ya da bir ses dosyası (m4a, mp3, wav, …) sürükleyip bırakın.
- **Kalite:** *Standart* (hızlı) veya *Yüksek* (large-v3-turbo, daha doğru, daha yavaş).
- Mikrofon kayıtları `Belgeler/Ders Transkript` klasörüne kaydedilir.

## Geliştirme

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python transkript.py
```

Modeller `models/` altında beklenir (`.github/workflows/build.yml` içindeki indirme adımına bakın).
Yeni sürüm yayımlamak: `git tag v1.0 && git push origin v1.0`. GitHub Actions dört paketi derleyip
test eder ve Releases sayfasına yükler.
