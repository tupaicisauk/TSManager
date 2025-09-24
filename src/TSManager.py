#!/usr/bin/env python3
# TSManager.v1.3.0 — LocalSync + Auto-Watch + Log History + Update Checker
# - Validasi ZIP (harus ada .lua & .manifest)
# - Clean .lua: hapus full-line comments yang diawali `--`, hapus README*, repack ZIP
# - Save langsung ke CLEAN_DIR, lalu copy ke DRIVE_DIR (Google Drive Desktop)
# - Auto-Watch: pantau folder untuk .zip baru; proses otomatis jika valid
# - Log & History: logs/tsmanager_log.csv + processed_md5.txt
# - Update Checker: tombol "Check Update" cek JSON versi terbaru, dapat unduh EXE baru

import os
import sys
import zipfile
import tempfile
import shutil
import threading
import queue
import datetime
import hashlib
import time
import csv
import tkinter as tk
from tkinter import messagebox, filedialog, Text

# --- optional deps for update checker ---
try:
    import requests  # bundled di exe; fallback ke urllib bila tidak ada
except Exception:
    requests = None
import webbrowser
import urllib.request

# ========= VERSION & UPDATE SOURCE =========
APP_VERSION = "1.3.0"
# Ganti dengan URL JSON kamu (host di GitHub Pages / Drive public / server)
# Format JSON yang di-host:
# {
#   "version": "1.3.0",
#   "changelog": "Tambah Auto-Update, Auto-Watch, Log History",
#   "url": "https://link-ke-TSManager_v1.3.0.exe"
# }
UPDATE_JSON_URL = "https://example.com/tsmanager/latest.json"

# ========= CONFIG & PATHS =========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CLEAN_DIR_FILE   = os.path.join(BASE_DIR, "CLEAN_DIR.txt")
DRIVE_DIR_FILE   = os.path.join(BASE_DIR, "DRIVE_DIR.txt")
WATCH_DIR_FILE   = os.path.join(BASE_DIR, "WATCH_DIR.txt")  # optional

LOGS_DIR         = os.path.join(BASE_DIR, "logs")
HISTORY_CSV      = os.path.join(LOGS_DIR, "tsmanager_log.csv")
PROCESSED_MD5_DB = os.path.join(BASE_DIR, "processed_md5.txt")  # satu md5 per baris

POLL_INTERVAL_S  = 5  # detik — interval Auto-Watch

# ========= UI LOGGER =========
class UILogger:
    def __init__(self, root: tk.Tk, text_widget: Text):
        self.root = root
        self.text = text_widget
        self.q = queue.Queue()
        self.text.configure(state="disabled")

    def log(self, msg: str):
        self.q.put(msg)

    def _drain(self):
        try:
            while True:
                msg = self.q.get_nowait()
                self.text.configure(state="normal")
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                self.text.insert("end", f"{timestamp}  {msg}\n")
                self.text.see("end")
                self.text.configure(state="disabled")
        except queue.Empty:
            pass

    def schedule(self, interval_ms: int = 200):
        self._drain()
        self.root.after(interval_ms, self.schedule, interval_ms)

    def call_ui(self, fn, *args, **kwargs):
        self.root.after(0, lambda: fn(*args, **kwargs))

# ========= HELPERS =========
def _ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p

def _read_path_optional(pathfile):
    if not os.path.exists(pathfile):
        return None
    with open(pathfile, "r", encoding="utf-8") as f:
        p = f.read().strip().strip('"')
    return p or None

def _write_path(pathfile, value):
    with open(pathfile, "w", encoding="utf-8") as f:
        f.write(value)

def _pick_and_save_dir(title, pathfile):
    sel = filedialog.askdirectory(title=title, mustexist=True)
    if sel:
        _write_path(pathfile, sel)
        return sel
    return None

def ensure_config_dir(pathfile, prompt_title):
    p = _read_path_optional(pathfile)
    if not p or not os.path.isdir(p):
        p = _pick_and_save_dir(prompt_title, pathfile)
        if not p:
            raise FileNotFoundError(f"{os.path.basename(pathfile)} belum dipilih.")
    return _ensure_dir(os.path.abspath(p))

def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):  # 1MB
            h.update(chunk)
    return h.hexdigest()

def copy_auto_replace(src, dst):
    """Copy src->dst: skip if identical MD5, else replace."""
    if os.path.exists(dst):
        try:
            if md5_file(src) == md5_file(dst):
                return "exists-identical"
        except Exception:
            pass
    _ensure_dir(os.path.dirname(dst))
    shutil.copy2(src, dst)
    return "copied"

# ========= HISTORY / LOGGING =========
def ensure_log_headers():
    _ensure_dir(LOGS_DIR)
    if not os.path.exists(HISTORY_CSV):
        with open(HISTORY_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "version", "action", "src_zip", "appid", "result",
                "zip_md5", "clean_target", "drive_target", "notes"
            ])

def append_log(action, src_zip, appid, result, zip_md5, clean_target, drive_target, notes):
    ensure_log_headers()
    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.datetime.now().isoformat(timespec="seconds"),
            APP_VERSION,
            action, src_zip, appid, result,
            zip_md5 or "", clean_target or "", drive_target or "", notes or ""
        ])

def load_processed_md5():
    s = set()
    if os.path.exists(PROCESSED_MD5_DB):
        with open(PROCESSED_MD5_DB, "r", encoding="utf-8") as f:
            for line in f:
                md5 = line.strip()
                if md5:
                    s.add(md5)
    return s

def add_processed_md5(val):
    with open(PROCESSED_MD5_DB, "a", encoding="utf-8") as f:
        f.write(val + "\n")

# ========= ZIP VALIDATION & CLEANER =========
def is_valid_manifest_zip(zip_path):
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            names = z.namelist()
            has_lua = any(n.lower().endswith(".lua") for n in names)
            has_manifest = any(n.lower().endswith(".manifest") for n in names)
            return has_lua and has_manifest
    except Exception:
        return False

def clean_lua_file(file_path: str):
    """Hapus baris yang diawali '--' (full-line comments)."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        cleaned = [ln for ln in lines if not ln.lstrip().startswith("--")]
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(cleaned)
    except Exception:
        pass

def process_zip_to_cleaned(zip_path: str):
    """
    Extract -> clean .lua -> remove README* -> repack ke zip baru di tempdir.
    Return (cleaned_zip_path, appid, tempdir)
    """
    appid = os.path.splitext(os.path.basename(zip_path))[0]
    temp_dir = tempfile.mkdtemp(prefix=f"ts_{appid}_")

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(temp_dir)

    for root, _, files in os.walk(temp_dir):
        for fn in files:
            full = os.path.join(root, fn)
            low = fn.lower()
            if low.endswith(".lua"):
                clean_lua_file(full)
            if low.startswith("readme"):
                try:
                    os.remove(full)
                except Exception:
                    pass

    out_zip = os.path.join(temp_dir, f"{appid}.zip")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z2:
        for root, _, files in os.walk(temp_dir):
            for fn in files:
                full = os.path.join(root, fn)
                if os.path.abspath(full) == os.path.abspath(out_zip):
                    continue
                arc = os.path.relpath(full, temp_dir)
                z2.write(full, arc)

    return out_zip, appid, temp_dir

# ========= CORE PROCESS =========
def process_one_zip(src, clean_dir, drive_dir, ui: UILogger):
    """Return result string."""
    try:
        # Validasi isi ZIP (wajib .lua + .manifest)
        if not is_valid_manifest_zip(src):
            ui.log(f"❌ Skip: {os.path.basename(src)} — Bukan manifest package, dilewati")
            append_log("validate", src, "", "skip_invalid", md5_file(src), "", "", "no .lua/.manifest")
            return "skip-invalid"

        zip_md5 = md5_file(src)
        cleaned_zip, appid, tmpdir = process_zip_to_cleaned(src)

        # Simpan ke CLEAN_DIR (no subfolder)
        clean_target = os.path.join(clean_dir, f"{appid}.zip")
        try:
            st_local = copy_auto_replace(cleaned_zip, clean_target)
            if st_local == "copied":
                ui.log(f"🧼 Saved cleaned to CLEAN_DIR: {os.path.basename(clean_target)}")
            else:
                ui.log(f"⏭️ Skip (identical already in CLEAN_DIR): {os.path.basename(clean_target)}")
        except Exception as e:
            ui.log(f"⚠️ Gagal salin ke CLEAN_DIR: {e}")

        # Copy ke Google Drive Desktop
        drive_target = os.path.join(drive_dir, f"{appid}.zip")
        drive_status = ""
        try:
            st = copy_auto_replace(clean_target, drive_target)
            if st == "copied":
                ui.log(f"✅ Copied to Drive: {os.path.basename(drive_target)}")
                drive_status = "copied"
            elif st == "exists-identical":
                ui.log(f"⏭️ Skip (identical on Drive): {os.path.basename(drive_target)}")
                drive_status = "exists-identical"
        except Exception as e:
            ui.log(f"❌ Copy to Drive folder failed: {e}")
            drive_status = f"copy-failed: {e}"

        append_log("process", src, appid, drive_status or "done", zip_md5, clean_target, drive_target, "")
        add_processed_md5(zip_md5)

        # Bersihkan tempdir
        try:
            if tmpdir and os.path.isdir(tmpdir):
                shutil.rmtree(tmpdir)
        except Exception:
            pass

        return drive_status or "done"

    except Exception as e:
        ui.log(f"❌ Failed: {os.path.basename(src)} -> {e}")
        append_log("error", src, "", "error", "", "", "", str(e))
        return "error"

# ========= AUTO-WATCH THREAD =========
class WatcherThread(threading.Thread):
    def __init__(self, watch_dir, clean_dir, drive_dir, ui: UILogger, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.watch_dir = watch_dir
        self.clean_dir = clean_dir
        self.drive_dir = drive_dir
        self.ui = ui
        self.stop_event = stop_event
        self.seen_md5 = load_processed_md5()  # md5 zip yang sudah pernah diproses
        self.seen_triplets = set()  # (path, size, mtime) per sesi

    def run(self):
        self.ui.log(f"👀 Auto-Watch aktif di: {self.watch_dir}")
        while not self.stop_event.is_set():
            try:
                for entry in os.scandir(self.watch_dir):
                    if not entry.is_file() or not entry.name.lower().endswith(".zip"):
                        continue

                    path = entry.path
                    try:
                        stat = entry.stat()
                        trip = (path, stat.st_size, int(stat.st_mtime))
                    except Exception:
                        trip = (path, 0, 0)

                    if trip in self.seen_triplets:
                        continue

                    try:
                        zmd5 = md5_file(path)
                    except Exception:
                        zmd5 = None

                    if zmd5 and zmd5 in self.seen_md5:
                        self.ui.log(f"⏭️ Auto-Watch skip: {os.path.basename(path)} (sudah pernah diproses)")
                        self.seen_triplets.add(trip)
                        continue

                    if not is_valid_manifest_zip(path):
                        self.ui.log(f"❌ Auto-Watch: {os.path.basename(path)} bukan manifest, dilewati")
                        append_log("validate", path, "", "skip_invalid", zmd5 or "", "", "", "no .lua/.manifest")
                        self.seen_triplets.add(trip)
                        continue

                    self.ui.log(f"▶️ Auto-Watch processing: {os.path.basename(path)}")
                    res = process_one_zip(path, self.clean_dir, self.drive_dir, self.ui)
                    if zmd5:
                        self.seen_md5.add(zmd5)
                    self.seen_triplets.add(trip)

                # jeda polling
                for _ in range(POLL_INTERVAL_S * 10):
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.1)

            except Exception as e:
                self.ui.log(f"⚠️ Auto-Watch error: {e}")
                time.sleep(POLL_INTERVAL_S)

        self.ui.log("🛑 Auto-Watch dimatikan.")

# ========= BATCH WORKER (manual) =========
def batch_worker_run(file_list, ui: UILogger):
    try:
        clean_dir = ensure_config_dir(CLEAN_DIR_FILE, "Pilih folder hasil cleaning (CLEAN_DIR)")
        drive_dir = ensure_config_dir(DRIVE_DIR_FILE, "Pilih folder Google Drive Desktop tujuan (DRIVE_DIR)")
        ui.log(f"Output (CLEAN_DIR): {clean_dir}")
        ui.log(f"Drive folder     : {drive_dir}")

        total = len(file_list)
        done = 0

        for src in file_list:
            src = src.strip().strip("{}").strip('"')
            if not src.lower().endswith(".zip"):
                ui.log(f"Skipping (not .zip): {src}")
                continue
            if not os.path.exists(src):
                ui.log(f"File not found: {src}")
                continue

            ui.log(f"Processing: {os.path.basename(src)}")
            process_one_zip(src, clean_dir, drive_dir, ui)

            done += 1
            ui.log(f"Progress: {done}/{total}")

        ui.log("All files processed.")

    except Exception as e:
        ui.log(f"❌ Fatal error: {e}")
        messagebox.showerror("Error", str(e))

# ========= UPDATE CHECKER =========
def fetch_json(url, timeout=10):
    try:
        if requests is not None:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            return r.json()
        # fallback urllib
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            import json
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Gagal ambil info update: {e}")

def download_file(url, dest, ui: UILogger, timeout=30):
    try:
        if requests is not None:
            with requests.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                done = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 15):
                        if chunk:
                            f.write(chunk)
                            done += len(chunk)
                            if total:
                                pct = int(done * 100 / total)
                                ui.log(f"⬇️ Downloading update… {pct}%")
        else:
            urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        ui.log(f"❌ Gagal download update: {e}")
        return False

def check_update(ui: UILogger, root: tk.Tk):
    ui.log("🔄 Checking update…")
    try:
        info = fetch_json(UPDATE_JSON_URL, timeout=12)
        latest = str(info.get("version") or "").strip()
        dl_url = str(info.get("url") or "").strip()
        changelog = str(info.get("changelog") or "").strip()

        if not latest:
            messagebox.showwarning("Update", "Info versi tidak valid.")
            return

        if latest == APP_VERSION:
            ui.log("✅ Sudah versi terbaru.")
            messagebox.showinfo("Up to date", f"TSManager {APP_VERSION} sudah versi terbaru.")
            return

        msg = f"Versi terbaru tersedia: {latest}\n\nChangelog:\n{changelog}\n\nUnduh dan jalankan versi baru?"
        if not messagebox.askyesno("Update Available", msg):
            return

        if not dl_url:
            # kalau URL kosong, buka halaman info
            webbrowser.open(UPDATE_JSON_URL)
            return

        # download ke file TSManager_new.exe di folder yang sama
        new_name = f"TSManager_v{latest}.exe"
        dest = os.path.join(BASE_DIR, new_name)
        ok = download_file(dl_url, dest, ui)
        if not ok or not os.path.exists(dest):
            messagebox.showerror("Update", "Gagal mengunduh versi baru.")
            return

        ui.log(f"✅ Update diunduh: {dest}")
        messagebox.showinfo(
            "Update",
            f"Berhasil mengunduh {new_name}.\nTutup aplikasi ini, kemudian jalankan file tersebut.\n"
            "Kamu bisa mengganti (rename) file baru menjadi nama exe lama jika mau replace."
        )
        # buka folder agar user mudah menemukan file
        try:
            os.startfile(BASE_DIR)
        except Exception:
            pass

    except Exception as e:
        ui.log(f"❌ Update check failed: {e}")
        messagebox.showerror("Update", str(e))

# ========= GUI =========
def build_gui():
    root = tk.Tk()
    root.title(f"TSManager.v{APP_VERSION} — LocalSync + Auto-Watch + History + Update")
    root.geometry("940x600")

    info = tk.Label(root, text=(
        "Pilih banyak file .zip atau aktifkan Auto-Watch untuk memantau folder.\n"
        "Validasi ZIP: harus mengandung .lua dan .manifest. README akan dihapus saat cleaning.\n"
        "Hasil clean → CLEAN_DIR, lalu copy ke DRIVE_DIR (Google Drive Desktop)."
    ))
    info.pack(pady=8)

    selected = tk.StringVar(value="No files selected.")
    lbl_sel = tk.Label(root, textvariable=selected, anchor="w", justify="left")
    lbl_sel.pack(fill="x", padx=12)

    # Baris tombol utama
    row = tk.Frame(root)
    row.pack(pady=6)

    def choose_files():
        files = filedialog.askopenfilenames(title="Select ZIP files", filetypes=[("ZIP files", "*.zip")])
        if files:
            selected.set("\n".join(files))

    tk.Button(row, text="📂 Choose .zip files (multi)", command=choose_files).pack(side="left", padx=5)

    def set_clean_dir():
        p = _pick_and_save_dir("Pilih folder hasil cleaning (CLEAN_DIR)", CLEAN_DIR_FILE)
        if p:
            ui.log(f"Set CLEAN_DIR: {p}")

    def set_drive_dir():
        p = _pick_and_save_dir("Pilih folder Google Drive Desktop (DRIVE_DIR)", DRIVE_DIR_FILE)
        if p:
            ui.log(f"Set DRIVE_DIR: {p}")

    tk.Button(row, text="🗂 Set CLEAN_DIR", command=set_clean_dir).pack(side="left", padx=5)
    tk.Button(row, text="🗂 Set DRIVE_DIR", command=set_drive_dir).pack(side="left", padx=5)
    tk.Button(row, text="🔄 Check Update", command=lambda: check_update(ui, root)).pack(side="left", padx=5)

    # Auto-Watch controls
    watch_frame = tk.Frame(root)
    watch_frame.pack(pady=6)

    watcher_stop_event = threading.Event()
    watcher_thread = {"ref": None}

    def set_watch_dir():
        p = _pick_and_save_dir("Pilih folder untuk Auto-Watch (pantau .zip)", WATCH_DIR_FILE)
        if p:
            ui.log(f"Set WATCH_DIR: {p}")

    tk.Button(watch_frame, text="👀 Set WATCH_DIR", command=set_watch_dir).pack(side="left", padx=5)

    def toggle_watch():
        if watcher_thread["ref"] and watcher_thread["ref"].is_alive():
            watcher_stop_event.set()
            watcher_thread["ref"] = None
            btn_watch.config(text="▶ Start Auto-Watch")
            return

        clean_dir = ensure_config_dir(CLEAN_DIR_FILE, "Pilih folder hasil cleaning (CLEAN_DIR)")
        drive_dir = ensure_config_dir(DRIVE_DIR_FILE, "Pilih folder Google Drive Desktop (DRIVE_DIR)")
        watch_dir = _read_path_optional(WATCH_DIR_FILE)
        if not watch_dir or not os.path.isdir(watch_dir):
            watch_dir = _pick_and_save_dir("Pilih folder untuk Auto-Watch (pantau .zip)", WATCH_DIR_FILE)
            if not watch_dir:
                messagebox.showwarning("Warning", "WATCH_DIR belum dipilih.")
                return

        watcher_stop_event.clear()
        t = WatcherThread(watch_dir, clean_dir, drive_dir, ui, watcher_stop_event)
        t.start()
        watcher_thread["ref"] = t
        btn_watch.config(text="⏹ Stop Auto-Watch")

    btn_watch = tk.Button(watch_frame, text="▶ Start Auto-Watch", command=toggle_watch)
    btn_watch.pack(side="left", padx=5)

    # Text log
    txt = tk.Text(root, height=20)
    txt.pack(fill="both", expand=True, padx=12, pady=8)
    ui = UILogger(root, txt)
    ui.schedule(200)

    # Run button
    def run_now():
        files = []
        cur = selected.get().strip()
        if cur and cur != "No files selected.":
            files.extend([line for line in cur.splitlines() if line.strip()])
        argv_files = [a for a in sys.argv[1:] if os.path.exists(a) and a.lower().endswith(".zip")]
        files.extend(argv_files)

        clean_list = []
        seen = set()
        for f in files:
            p = os.path.abspath(f)
            if p not in seen:
                seen.add(p)
                clean_list.append(p)

        if not clean_list:
            messagebox.showwarning("Warning", "No .zip files selected.")
            return

        threading.Thread(target=batch_worker_run, args=(clean_list, ui), daemon=True).start()
        ui.log(f"Started processing {len(clean_list)} file(s)…")

    tk.Button(root, text="▶️ Run", command=run_now).pack(pady=4)

    # Footer
    cfg = tk.Label(root, text=(
        f"Version: {APP_VERSION}  •  Log: logs/tsmanager_log.csv  •  Riwayat ZIP: processed_md5.txt  •  Auto-Watch: {POLL_INTERVAL_S}s"
    ))
    cfg.pack(pady=4)

    def on_close():
        if watcher_thread["ref"] and watcher_thread["ref"].is_alive():
            watcher_stop_event.set()
            time.sleep(0.2)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    return root

# ========= MAIN =========
if __name__ == "__main__":
    _ensure_dir(LOGS_DIR)
    ensure_log_headers()
    app = build_gui()
    app.mainloop()
