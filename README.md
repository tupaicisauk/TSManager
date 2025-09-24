# 🚀 TechStation Manager (TSManager)

**TSManager** adalah aplikasi untuk mengelola file manifest dengan cepat dan aman.  
Fitur utama: cleaning file `.lua`, repack `.zip`, auto-sync ke Google Drive, dan notifikasi bawaan.  

---

## ✨ Fitur Utama
- 🧼 **Cleaning**: Hapus komentar `--` di file `.lua` dan otomatis hapus `README`.  
- 📦 **Repack**: Rezip hasil cleaning tanpa mengubah `.manifest`.  
- ☁️ **Auto-Sync**: Copy hasil cleaning langsung ke folder Google Drive Desktop.  
- 🔎 **Auto-Watch** *(v1.3.0+)*: Pantau folder input, otomatis proses file baru.  
- 📜 **Log & History** *(v1.3.0+)*: Simpan log setiap proses (sukses/gagal).  
- 🔄 **Update Checker** *(v1.3.0+)*: Cek versi terbaru & update langsung dari aplikasi.  

---

## 📂 Struktur Repo
```
TSManager/
 ├─ src/                # Source code utama (.py)
 ├─ icons/              # Ikon aplikasi
 ├─ updates/            # Metadata update
 │    └─ latest.json
 ├─ README.md           # Panduan repo (file ini)
 └─ CHANGELOG.md        # Catatan perubahan
```

---

## 🔑 Cara Pakai (Staff)
1. Jalankan `TSManager.exe` (sudah dikompilasi oleh admin).  
2. Pilih file `.zip` atau gunakan Auto-Watch folder.  
3. Klik **Run** → tunggu hingga proses selesai.  
4. Hasil akan otomatis masuk ke folder **clean** + sinkron ke Google Drive.  

> 📄 Panduan staff lebih lengkap ada di **README_STAFF.txt** (dibagikan bersama aplikasi).  

---

## 🛠 Cara Update Versi
1. Admin build `.exe` baru menggunakan PyInstaller.  
2. Upload ke **GitHub Releases**.  
3. Update `updates/latest.json` dengan link release terbaru.  
4. Staff tinggal klik tombol **Update** di aplikasi → otomatis download & replace.  

Contoh `latest.json`:  
```json
{
  "version": "1.3.0",
  "changelog": "✨ Tambah Auto-Watch, Log History, Update Checker",
  "url": "https://github.com/<username>/<repo>/releases/download/v1.3.0/TSManager_v1.3.0.exe"
}
```

---

## 📜 Lisensi
Project internal **TechStation**.  
Tidak untuk distribusi publik tanpa izin.  
