# 📜 Changelog — TechStation Manager

Semua perubahan besar pada project ini akan dicatat di file ini.  
Format mengikuti [Keep a Changelog](https://keepachangelog.com/) dan versi mengikuti [Semantic Versioning](https://semver.org/).  

---

## [1.3.0] - 2025-09-25
### ✨ Added
- **Auto-Watch**: otomatis memantau folder input, langsung proses `.zip` baru.  
- **Log & History**: simpan hasil proses (sukses/gagal) ke file log.  
- **Update Checker**: tombol update → download versi terbaru dari GitHub.  

---

## [1.1.5] - 2025-09-20
### ✨ Added
- Mode **LocalSync**: hasil cleaning otomatis di-copy ke Google Drive Desktop folder.  
- **Auto-Replace**: file di Drive diganti hanya jika berbeda (cek MD5).  
- Popup notifikasi sukses / gagal lebih informatif.  

---

## [1.1.3] - 2025-09-18
### 🛠 Changed
- Perbaikan repack `.zip` agar hasil lebih rapi.  
- Hapus folder ganda di dalam `clean/`, output langsung `.zip`.  
- Tambah log skip jika file identik dengan versi di Drive.  

---

## [1.1.1] - 2025-09-15
### ✨ Added
- Cleaning `.lua` (hapus komentar `--`)  
- Hapus file `README` dalam zip.  
- Repack otomatis ke `.zip` baru.  
- Upload ke Google Drive via API.  
- GUI sederhana dengan log & popup.  

---

## [1.0.0] - 2025-09-10
### 🎉 First Release
- Versi dasar TSManager.  
- Fitur cleaning `.lua` & repack `.zip`.  
