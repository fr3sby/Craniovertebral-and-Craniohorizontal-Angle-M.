import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import ExifTags, Image, ImageTk


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
DB_FILE_NAME = "angle_measurements.db"
EXCEL_FILE_NAME = "angle_measurements.xlsx"


@dataclass
class LandmarkSet:
    c7: Optional[Tuple[float, float]] = None
    tragus: Optional[Tuple[float, float]] = None
    cantus: Optional[Tuple[float, float]] = None


class CranioAngleApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Craniovertebral / Cranial Rotation / Craniohorizontal Ölçüm Aracı")
        self.root.geometry("1400x850")

        self.folder: Optional[Path] = None
        self.images: list[Path] = []
        self.current_image_path: Optional[Path] = None

        self.db_conn: Optional[sqlite3.Connection] = None

        self.landmarks_by_image: Dict[str, LandmarkSet] = {}
        self.angle_cache: Dict[str, Dict[str, float]] = {}

        self.current_landmarks = LandmarkSet()
        self.current_drag_point: Optional[str] = None

        self.original_image: Optional[Image.Image] = None
        self.tk_image: Optional[ImageTk.PhotoImage] = None
        self.display_size = (1000, 700)
        self.scale_x = 1.0
        self.scale_y = 1.0

        self._configure_style()
        self._build_ui()

    def _configure_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f6f7fb")
        style.configure("TLabel", background="#f6f7fb", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"), foreground="#1a3d7c")
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=7)

    def _build_ui(self):
        wrapper = ttk.Frame(self.root, padding=10)
        wrapper.pack(fill="both", expand=True)

        top_bar = ttk.Frame(wrapper)
        top_bar.pack(fill="x", pady=(0, 10))

        ttk.Label(top_bar, text="Klasör seçip fotoğrafları tek tek işaretleyin.", style="Title.TLabel").pack(side="left")
        ttk.Button(top_bar, text="📂 Klasör Seç", command=self.select_folder).pack(side="right")

        body = ttk.Frame(wrapper)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=4)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(body, padding=8)
        left_panel.grid(row=0, column=0, sticky="nsew")
        ttk.Label(left_panel, text="Fotoğraflar", style="Header.TLabel").pack(anchor="w", pady=(0, 6))

        self.image_listbox = tk.Listbox(left_panel, font=("Segoe UI", 10), activestyle="dotbox")
        self.image_listbox.pack(fill="both", expand=True)
        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)

        center_panel = ttk.Frame(body, padding=8)
        center_panel.grid(row=0, column=1, sticky="nsew")
        center_panel.rowconfigure(1, weight=1)
        center_panel.columnconfigure(0, weight=1)

        self.instructions_var = tk.StringVar(
            value="Sıra: C7 → Tragus → Cantus. Sonrasında noktaları sürükleyerek düzeltin."
        )
        center_panel.rowconfigure(0, minsize=34)
        ttk.Label(center_panel, textvariable=self.instructions_var, style="Header.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )

        self.canvas = tk.Canvas(center_panel, bg="#1f1f1f", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<ButtonPress-1>", self.on_drag_start, add="+")
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_end)

        right_panel = ttk.Frame(body, padding=8)
        right_panel.grid(row=0, column=2, sticky="nsew")

        ttk.Label(right_panel, text="Açı Sonuçları", style="Header.TLabel").pack(anchor="w", pady=(0, 8))

        self.cv_var = tk.StringVar(value="CV Açısı: -")
        self.cr_var = tk.StringVar(value="CR Açısı: -")
        self.ch_var = tk.StringVar(value="CH Açısı: -")
        self.point_status_var = tk.StringVar(value="Nokta durumu: C7, Tragus, Cantus bekleniyor")

        ttk.Label(right_panel, textvariable=self.cv_var).pack(anchor="w", pady=4)
        ttk.Label(right_panel, textvariable=self.cr_var).pack(anchor="w", pady=4)
        ttk.Label(right_panel, textvariable=self.ch_var).pack(anchor="w", pady=4)
        ttk.Label(right_panel, textvariable=self.point_status_var, wraplength=250).pack(anchor="w", pady=4)

        ttk.Separator(right_panel, orient="horizontal").pack(fill="x", pady=10)

        self.meta_var = tk.StringVar(value="Görsel tarihi: -")
        ttk.Label(right_panel, textvariable=self.meta_var, wraplength=250).pack(anchor="w", pady=4)

        ttk.Button(right_panel, text="💾 Bu Görseli Kaydet", command=self.save_current_measurement).pack(
            fill="x", pady=(16, 6)
        )
        ttk.Button(right_panel, text="📊 Tümünü Excel'e Aktar", command=self.export_to_excel).pack(fill="x", pady=6)

        ttk.Label(
            right_panel,
            text="Noktaları sürükleyerek düzeltin. Açılar anlık güncellenir.",
            wraplength=250,
        ).pack(anchor="w", pady=(15, 0))

    def select_folder(self):
        selected = filedialog.askdirectory(title="Fotoğraf klasörünü seçin")
        if not selected:
            return

        folder = Path(selected)
        images = sorted([p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS])
        if not images:
            messagebox.showwarning("Uyarı", "Seçilen klasörde desteklenen görsel bulunamadı.")
            return

        self.folder = folder
        self.images = images
        self._open_database()
        self._load_all_saved_measurements()

        self.image_listbox.delete(0, tk.END)
        for img in images:
            self.image_listbox.insert(tk.END, img.name)

        self.image_listbox.selection_clear(0, tk.END)
        self.image_listbox.selection_set(0)
        self.on_image_select(None)

    def _open_database(self):
        if self.folder is None:
            return
        db_path = self.folder / DB_FILE_NAME
        self.db_conn = sqlite3.connect(db_path)
        self.db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                image_name TEXT PRIMARY KEY,
                image_path TEXT NOT NULL,
                capture_date TEXT,
                c7_x REAL,
                c7_y REAL,
                tragus_x REAL,
                tragus_y REAL,
                cantus_x REAL,
                cantus_y REAL,
                cv_angle REAL,
                cr_angle REAL,
                ch_angle REAL,
                updated_at TEXT
            )
            """
        )
        self.db_conn.commit()

    def _load_all_saved_measurements(self):
        self.landmarks_by_image.clear()
        self.angle_cache.clear()
        if self.db_conn is None:
            return

        rows = self.db_conn.execute(
            "SELECT image_name, c7_x, c7_y, tragus_x, tragus_y, cantus_x, cantus_y, cv_angle, cr_angle, ch_angle FROM measurements"
        ).fetchall()

        for row in rows:
            image_name, c7x, c7y, tx, ty, cax, cay, cv, cr, ch = row
            landmarks = LandmarkSet(
                c7=(c7x, c7y) if c7x is not None and c7y is not None else None,
                tragus=(tx, ty) if tx is not None and ty is not None else None,
                cantus=(cax, cay) if cax is not None and cay is not None else None,
            )
            self.landmarks_by_image[image_name] = landmarks
            if cv is not None and cr is not None and ch is not None:
                self.angle_cache[image_name] = {"cv": cv, "cr": cr, "ch": ch}

    def on_image_select(self, _event):
        if not self.images:
            return

        selected = self.image_listbox.curselection()
        if not selected:
            return

        image_path = self.images[selected[0]]
        self.current_image_path = image_path
        self._load_image(image_path)

        self.current_landmarks = self.landmarks_by_image.get(image_path.name, LandmarkSet())
        self._update_ui_metadata(image_path)
        self._render_canvas()
        self._update_angle_outputs()

    def _load_image(self, image_path: Path):
        image = Image.open(image_path).convert("RGB")
        self.original_image = image

        canvas_w = max(self.canvas.winfo_width(), 600)
        canvas_h = max(self.canvas.winfo_height(), 500)

        img_w, img_h = image.size
        ratio = min(canvas_w / img_w, canvas_h / img_h)
        disp_w = int(img_w * ratio)
        disp_h = int(img_h * ratio)

        self.display_size = (disp_w, disp_h)
        self.scale_x = img_w / disp_w
        self.scale_y = img_h / disp_h

        resized = image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized)

    def _image_offset(self) -> Tuple[int, int]:
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        disp_w, disp_h = self.display_size
        x0 = max((canvas_w - disp_w) // 2, 0)
        y0 = max((canvas_h - disp_h) // 2, 0)
        return x0, y0

    def _to_canvas(self, point: Tuple[float, float]) -> Tuple[float, float]:
        x0, y0 = self._image_offset()
        return x0 + point[0] / self.scale_x, y0 + point[1] / self.scale_y

    def _to_image(self, x_canvas: float, y_canvas: float) -> Tuple[float, float]:
        x0, y0 = self._image_offset()
        x = (x_canvas - x0) * self.scale_x
        y = (y_canvas - y0) * self.scale_y
        if self.original_image:
            w, h = self.original_image.size
            x = min(max(x, 0), w)
            y = min(max(y, 0), h)
        return x, y

    def _render_canvas(self):
        self.canvas.delete("all")
        if not self.tk_image:
            return

        x0, y0 = self._image_offset()
        disp_w, disp_h = self.display_size

        self.canvas.create_image(x0, y0, image=self.tk_image, anchor="nw")
        self.canvas.create_rectangle(x0, y0, x0 + disp_w, y0 + disp_h, outline="#2f2f2f")

        self._draw_geometry()
        self._draw_points()

    def _draw_points(self):
        colors = {
            "c7": "#ff5a5a",
            "tragus": "#52d17a",
            "cantus": "#57a0ff",
        }

        for name in ["c7", "tragus", "cantus"]:
            point = getattr(self.current_landmarks, name)
            if not point:
                continue
            x, y = self._to_canvas(point)
            self.canvas.create_oval(x - 6, y - 6, x + 6, y + 6, fill=colors[name], outline="white", width=1)
            self.canvas.create_text(x + 12, y - 10, text=name.upper(), fill="white", anchor="w", font=("Segoe UI", 9, "bold"))

    def _draw_geometry(self):
        c7 = self.current_landmarks.c7
        tragus = self.current_landmarks.tragus
        cantus = self.current_landmarks.cantus

        if c7 and tragus:
            x1, y1 = self._to_canvas(c7)
            x2, y2 = self._to_canvas(tragus)
            self.canvas.create_line(x1, y1, x2, y2, fill="#ffcb47", width=2)
            self.canvas.create_line(x1 - 120, y1, x1 + 120, y1, fill="#8ad9ff", width=2, dash=(4, 4))

        if tragus and cantus:
            x1, y1 = self._to_canvas(tragus)
            x2, y2 = self._to_canvas(cantus)
            self.canvas.create_line(x1, y1, x2, y2, fill="#ff6ed9", width=2)
            self.canvas.create_line(x1 - 120, y1, x1 + 120, y1, fill="#8ad9ff", width=2, dash=(4, 4))

    def on_canvas_click(self, event):
        if not self.current_image_path or not self.original_image:
            return

        x0, y0 = self._image_offset()
        disp_w, disp_h = self.display_size
        if not (x0 <= event.x <= x0 + disp_w and y0 <= event.y <= y0 + disp_h):
            return

        x, y = self._to_image(event.x, event.y)

        if self.current_landmarks.c7 is None:
            self.current_landmarks.c7 = (x, y)
        elif self.current_landmarks.tragus is None:
            self.current_landmarks.tragus = (x, y)
        elif self.current_landmarks.cantus is None:
            self.current_landmarks.cantus = (x, y)

        self._save_landmarks_to_memory()
        self._render_canvas()
        self._update_angle_outputs()
        self._auto_save_if_complete()

    def on_drag_start(self, event):
        self.current_drag_point = None
        for name in ["c7", "tragus", "cantus"]:
            point = getattr(self.current_landmarks, name)
            if not point:
                continue
            cx, cy = self._to_canvas(point)
            if (event.x - cx) ** 2 + (event.y - cy) ** 2 <= 12 ** 2:
                self.current_drag_point = name
                break

    def on_drag_motion(self, event):
        if not self.current_drag_point:
            return
        if not self.current_image_path or not self.original_image:
            return

        x, y = self._to_image(event.x, event.y)
        setattr(self.current_landmarks, self.current_drag_point, (x, y))
        self._save_landmarks_to_memory()
        self._render_canvas()
        self._update_angle_outputs()
        self._auto_save_if_complete()

    def on_drag_end(self, _event):
        self.current_drag_point = None

    def _save_landmarks_to_memory(self):
        if self.current_image_path:
            self.landmarks_by_image[self.current_image_path.name] = LandmarkSet(
                c7=self.current_landmarks.c7,
                tragus=self.current_landmarks.tragus,
                cantus=self.current_landmarks.cantus,
            )

    @staticmethod
    def _acute_angle_to_horizontal(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        angle = abs(math.degrees(math.atan2(dy, dx)))
        if angle > 90:
            angle = 180 - angle
        return angle

    @staticmethod
    def _angle_between(v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        n1 = math.hypot(v1[0], v1[1])
        n2 = math.hypot(v2[0], v2[1])
        if n1 == 0 or n2 == 0:
            return 0.0
        cos_theta = max(min(dot / (n1 * n2), 1.0), -1.0)
        return math.degrees(math.acos(cos_theta))

    def _calculate_angles(self) -> Optional[Dict[str, float]]:
        c7 = self.current_landmarks.c7
        tragus = self.current_landmarks.tragus
        cantus = self.current_landmarks.cantus
        if not (c7 and tragus and cantus):
            return None

        cv = self._acute_angle_to_horizontal(c7, tragus)
        ch = self._acute_angle_to_horizontal(tragus, cantus)

        v1 = (c7[0] - tragus[0], c7[1] - tragus[1])
        v2 = (cantus[0] - tragus[0], cantus[1] - tragus[1])
        cr = self._angle_between(v1, v2)

        return {"cv": cv, "cr": cr, "ch": ch}

    def _update_angle_outputs(self):
        angles = self._calculate_angles()
        if not angles:
            self.cv_var.set("CV Açısı: -")
            self.cr_var.set("CR Açısı: -")
            self.ch_var.set("CH Açısı: -")
            missing = []
            if self.current_landmarks.c7 is None:
                missing.append("C7")
            if self.current_landmarks.tragus is None:
                missing.append("Tragus")
            if self.current_landmarks.cantus is None:
                missing.append("Cantus")
            self.point_status_var.set("Eksik nokta: " + ", ".join(missing))
            return

        self.cv_var.set(f"CV Açısı: {angles['cv']:.2f}°")
        self.cr_var.set(f"CR Açısı: {angles['cr']:.2f}°")
        self.ch_var.set(f"CH Açısı: {angles['ch']:.2f}°")
        self.point_status_var.set("Tüm noktalar tamam. Sürükleyerek ince ayar yapabilirsiniz.")

        if self.current_image_path:
            self.angle_cache[self.current_image_path.name] = angles

    def _extract_capture_date(self, image_path: Path) -> str:
        try:
            image = Image.open(image_path)
            exif = image.getexif()
            if exif:
                exif_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                for key in ["DateTimeOriginal", "DateTimeDigitized", "DateTime"]:
                    if key in exif_map and exif_map[key]:
                        raw = str(exif_map[key])
                        try:
                            dt = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
                            return dt.isoformat(sep=" ")
                        except ValueError:
                            return raw
        except Exception:
            pass

        ts = image_path.stat().st_mtime
        return datetime.fromtimestamp(ts).isoformat(sep=" ", timespec="seconds")

    def _update_ui_metadata(self, image_path: Path):
        capture_date = self._extract_capture_date(image_path)
        self.meta_var.set(f"Görsel tarihi: {capture_date}")

    def _auto_save_if_complete(self):
        if self._calculate_angles():
            self._write_current_measurement_to_db(show_popup=False)

    def save_current_measurement(self):
        if not self.current_image_path:
            messagebox.showwarning("Uyarı", "Önce bir görsel seçin.")
            return

        if not self._calculate_angles():
            messagebox.showwarning("Uyarı", "Kaydetmek için C7, Tragus ve Cantus noktalarını tamamlayın.")
            return

        self._write_current_measurement_to_db(show_popup=True)

    def _write_current_measurement_to_db(self, show_popup: bool = False):
        if self.db_conn is None or self.current_image_path is None:
            return

        angles = self._calculate_angles()
        if angles is None:
            return

        capture_date = self._extract_capture_date(self.current_image_path)
        c7 = self.current_landmarks.c7
        tragus = self.current_landmarks.tragus
        cantus = self.current_landmarks.cantus

        self.db_conn.execute(
            """
            INSERT INTO measurements (
                image_name, image_path, capture_date,
                c7_x, c7_y, tragus_x, tragus_y, cantus_x, cantus_y,
                cv_angle, cr_angle, ch_angle, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(image_name) DO UPDATE SET
                image_path = excluded.image_path,
                capture_date = excluded.capture_date,
                c7_x = excluded.c7_x,
                c7_y = excluded.c7_y,
                tragus_x = excluded.tragus_x,
                tragus_y = excluded.tragus_y,
                cantus_x = excluded.cantus_x,
                cantus_y = excluded.cantus_y,
                cv_angle = excluded.cv_angle,
                cr_angle = excluded.cr_angle,
                ch_angle = excluded.ch_angle,
                updated_at = excluded.updated_at
            """,
            (
                self.current_image_path.name,
                str(self.current_image_path),
                capture_date,
                c7[0],
                c7[1],
                tragus[0],
                tragus[1],
                cantus[0],
                cantus[1],
                angles["cv"],
                angles["cr"],
                angles["ch"],
                datetime.now().isoformat(sep=" ", timespec="seconds"),
            ),
        )
        self.db_conn.commit()

        if show_popup:
            messagebox.showinfo("Kaydedildi", f"{self.current_image_path.name} için ölçüm kaydedildi.")

    def export_to_excel(self):
        if self.db_conn is None or self.folder is None:
            messagebox.showwarning("Uyarı", "Önce klasör seçin.")
            return

        rows = self.db_conn.execute(
            """
            SELECT image_name, capture_date, cv_angle, cr_angle, ch_angle
            FROM measurements
            ORDER BY image_name
            """
        ).fetchall()

        if not rows:
            messagebox.showwarning("Uyarı", "Excel'e aktarılacak kayıt yok.")
            return

        try:
            import pandas as pd

            df = pd.DataFrame(
                rows,
                columns=["Gorsel Adi", "Gorsel Tarihi", "CV Acisi", "CR Acisi", "CH Acisi"],
            )
            excel_path = self.folder / EXCEL_FILE_NAME
            df.to_excel(excel_path, index=False)
            messagebox.showinfo("Başarılı", f"Excel dosyası oluşturuldu:\n{excel_path}")
        except Exception as e:
            messagebox.showerror("Hata", f"Excel aktarımı sırasında hata oluştu:\n{e}")


def main():
    root = tk.Tk()
    app = CranioAngleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
