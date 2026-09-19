import os
import shutil
import datetime
from pathlib import Path

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle

try:
    from android.permissions import request_permissions, check_permission, Permission
    from android import mActivity
    from jnius import autoclass
    ON_ANDROID = True
except ImportError:
    ON_ANDROID = False

# Material 3 Tonal Palette (RGBA 0.0 - 1.0)
COLOR_BG = (0.07, 0.07, 0.09, 1.0)           # #121316
COLOR_SURFACE = (0.10, 0.11, 0.12, 1.0)      # #1a1c1e
COLOR_SURFACE_CARD = (0.12, 0.13, 0.14, 1.0) # #1e2024
COLOR_PRIMARY = (0.66, 0.78, 0.98, 1.0)      # #a8c7fa
COLOR_ON_PRIMARY = (0.02, 0.20, 0.35, 1.0)   # #063259
COLOR_CONTAINER = (0.20, 0.27, 0.33, 1.0)    # #334454
COLOR_CONTAINER_ACTIVE = (0.25, 0.35, 0.45, 1.0)
COLOR_TEXT_HIGH = (0.89, 0.89, 0.90, 1.0)    # #e2e2e6
COLOR_TEXT_MED = (0.60, 0.63, 0.65, 1.0)     # #9aa0a6
COLOR_SUCCESS = (0.08, 0.22, 0.14, 1.0)      # #143823
COLOR_SUCCESS_TEXT = (0.73, 0.95, 0.78, 1.0)
COLOR_ERROR = (0.29, 0.11, 0.11, 1.0)        # #4a1c1d
COLOR_ERROR_TEXT = (0.95, 0.72, 0.71, 1.0)
COLOR_DISABLED_BG = (0.14, 0.15, 0.16, 1.0)
COLOR_DISABLED_FG = (0.33, 0.35, 0.39, 1.0)

SAVE_EXTENSIONS = {".srm", ".sav"}
BASE_STATE_EXTS = {".state"} | {f".state{i}" for i in range(10)}

def classify_file_type(name: str):
    lower = name.lower()
    if lower.endswith(".state.auto") or lower.endswith(".state.png"):
        return "Auto State"
    if any(lower.endswith(ext) for ext in SAVE_EXTENSIONS):
        return "Battery Save"
    if Path(lower).suffix in BASE_STATE_EXTS or lower.endswith(".state"):
        return "Save State"
    return "Other"

def flush_disk_caches():
    try:
        if hasattr(os, "sync"):
            os.sync()
        os.system("sync")
    except Exception:
        pass

def find_miyoo_sd_roots():
    storage_root = Path("/storage")
    if not storage_root.exists():
        return None, None, None
    for item in storage_root.iterdir():
        if item.is_dir() and item.name not in ["emulated", "self", "enc_emulated"]:
            profile_dir = item / "Saves" / "CurrentProfile"
            if profile_dir.exists():
                saves_path = profile_dir / "saves"
                states_path = profile_dir / "states"
                return (
                    saves_path if saves_path.exists() else None,
                    states_path if states_path.exists() else None,
                    item
                )
    return None, None, None

# Common RetroArch save/state locations across different install methods.
# The plain "RetroArch/saves" layout covers a sideloaded/legacy install;
# the "Android/data/..." paths cover RetroArch installed from the Play
# Store on Android 11+, where apps are sandboxed into their own folder.
RETROARCH_SAVE_SUBDIRS = [
    "RetroArch/saves",
    "Android/data/com.retroarch.aarch64/files/saves",
    "Android/data/com.retroarch/files/saves",
]
RETROARCH_STATE_SUBDIRS = [
    "RetroArch/states",
    "Android/data/com.retroarch.aarch64/files/states",
    "Android/data/com.retroarch/files/states",
]

def find_android_roots():
    """Scan internal storage and any non-Miyoo SD card for a RetroArch
    install, checking every known save/state layout rather than a single
    hardcoded path. Renamed from the original find_nova_roots() — the old
    name referenced one specific handheld model but the logic itself was
    always generic RetroArch-on-Android scanning."""
    save_roots = []
    state_roots = []

    candidate_bases = [Path("/storage/emulated/0")]
    storage_root = Path("/storage")
    if storage_root.exists():
        for item in storage_root.iterdir():
            if item.is_dir() and item.name not in ["emulated", "self", "enc_emulated"]:
                if not (item / "Saves" / "CurrentProfile").exists():
                    candidate_bases.append(item)

    for base in candidate_bases:
        for sub in RETROARCH_SAVE_SUBDIRS:
            p = base / sub
            if p.exists() and p not in save_roots:
                save_roots.append(p)
        for sub in RETROARCH_STATE_SUBDIRS:
            p = base / sub
            if p.exists() and p not in state_roots:
                state_roots.append(p)

    return save_roots, state_roots

def has_all_files_access():
    """Check MANAGE_EXTERNAL_STORAGE ("All files access"), required on
    Android 11+ to read/write outside the app's own sandbox. Returns True
    on non-Android platforms so desktop testing isn't blocked."""
    if not ON_ANDROID:
        return True
    try:
        Environment = autoclass("android.os.Environment")
        return bool(Environment.isExternalStorageManager())
    except Exception:
        return False

def open_all_files_access_settings():
    """Send the user straight to the system settings screen where they can
    grant All files access, instead of leaving them to hunt for it."""
    if not ON_ANDROID:
        return
    try:
        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
        intent.setData(Uri.parse("package:" + mActivity.getPackageName()))
        mActivity.startActivity(intent)
    except Exception:
        pass

def format_mtime(file_path):
    if file_path and file_path.exists():
        mtime = file_path.stat().st_mtime
        return datetime.datetime.fromtimestamp(mtime).strftime('%m/%d/%y %H:%M'), mtime
    return "[Missing]", 0


class SolidLayout(BoxLayout):
    """BoxLayout that renders a background color."""
    def __init__(self, bg_color, **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        with self.canvas.before:
            self.color_instruction = Color(*bg_color)
            self.rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def set_bg_color(self, color):
        self.bg_color = color
        self.color_instruction.rgba = color


class MiyooSyncApp(App):
    def build(self):
        Window.clearcolor = COLOR_BG
        self.title = "Miyoo Sync"

        if ON_ANDROID:
            try:
                request_permissions([
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                ])
            except Exception:
                pass

        self.miyoo_saves_path = None
        self.miyoo_states_path = None
        self.miyoo_sd_root = None

        self.active_filter = "ALL"
        self.all_scanned_items = []
        self.row_widgets = []

        # Root vertical layout
        root = BoxLayout(orientation="vertical", padding=[14, 10, 14, 10], spacing=8)

        # 1. Top App Bar
        app_bar = SolidLayout(COLOR_SURFACE, orientation="horizontal", size_hint_y=None, height=48, padding=[12, 6, 12, 6], spacing=10)
        
        title_label = Label(text="[b]Miyoo Sync[/b]", markup=True, font_size="17sp", color=COLOR_TEXT_HIGH, size_hint_x=None, width=120)
        app_bar.add_widget(title_label)

        self.status_chip = Label(
            text="Scanning USB-OTG...",
            font_size="12sp",
            color=COLOR_TEXT_MED,
            size_hint_x=0.5
        )
        app_bar.add_widget(self.status_chip)

        rescan_btn = Button(
            text="Rescan",
            font_size="12sp",
            size_hint_x=None,
            width=80,
            background_normal="",
            background_color=COLOR_CONTAINER,
            color=COLOR_TEXT_HIGH
        )
        rescan_btn.bind(on_release=lambda x: self.scan_and_preview())
        app_bar.add_widget(rescan_btn)

        eject_btn = Button(
            text="Eject SD",
            font_size="12sp",
            size_hint_x=None,
            width=85,
            background_normal="",
            background_color=COLOR_ERROR,
            color=COLOR_ERROR_TEXT
        )
        eject_btn.bind(on_release=lambda x: self.safely_eject())
        app_bar.add_widget(eject_btn)

        root.add_widget(app_bar)

        # 2. Filter Bar
        filter_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=36, spacing=6)
        self.filter_buttons = {}
        for key, title in [("ALL", "All"), ("SAVES", "Battery Saves"), ("STATES", "Save States")]:
            btn = Button(
                text=title,
                font_size="12sp",
                background_normal="",
                background_color=COLOR_CONTAINER_ACTIVE if key == "ALL" else COLOR_CONTAINER,
                color=COLOR_TEXT_HIGH
            )
            btn.bind(on_release=lambda inst, k=key: self.set_filter(k))
            self.filter_buttons[key] = btn
            filter_bar.add_widget(btn)

        root.add_widget(filter_bar)

        # 3. Table Header
        header = SolidLayout(COLOR_CONTAINER, orientation="horizontal", size_hint_y=None, height=30, padding=[8, 2, 8, 2])
        header.add_widget(Label(text="[b]TYPE[/b]", markup=True, font_size="11sp", size_hint_x=0.18, color=COLOR_TEXT_MED))
        header.add_widget(Label(text="[b]ITEM / GAME[/b]", markup=True, font_size="11sp", size_hint_x=0.38, color=COLOR_TEXT_MED))
        header.add_widget(Label(text="[b]MIYOO [M][/b]", markup=True, font_size="11sp", size_hint_x=0.18, color=COLOR_TEXT_MED))
        header.add_widget(Label(text="[b]DIRECTION[/b]", markup=True, font_size="11sp", size_hint_x=0.26, color=COLOR_TEXT_MED))
        root.add_widget(header)

        # 4. Scrollable Item List
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.list_layout = GridLayout(cols=1, spacing=4, size_hint_y=None)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

        # 5. Bottom Sync Action Button
        self.sync_button = Button(
            text="NO ITEMS TO SYNC",
            font_size="14sp",
            bold=True,
            size_hint_y=None,
            height=46,
            background_normal="",
            background_color=COLOR_DISABLED_BG,
            color=COLOR_DISABLED_FG,
            disabled=True
        )
        self.sync_button.bind(on_release=lambda x: self.execute_sync())
        root.add_widget(self.sync_button)

        self.scan_and_preview()
        return root

    def set_filter(self, mode):
        self.active_filter = mode
        for k, btn in self.filter_buttons.items():
            btn.background_color = COLOR_CONTAINER_ACTIVE if k == mode else COLOR_CONTAINER
        self.render_filtered_view()

    def show_popup(self, title, message):
        popup = Popup(
            title=title,
            content=Label(text=message, font_size="13sp", color=COLOR_TEXT_HIGH),
            size_hint=(0.8, 0.45)
        )
        popup.open()

    def safely_eject(self):
        if not self.miyoo_sd_root:
            self.show_popup("Eject", "No Miyoo SD Card is currently connected.")
            return

        flush_disk_caches()
        self.miyoo_saves_path = None
        self.miyoo_states_path = None
        self.miyoo_sd_root = None
        self.all_scanned_items.clear()
        self.list_layout.clear_widgets()

        self.status_chip.text = "Safely Ejected"
        self.status_chip.color = COLOR_TEXT_MED

        self.sync_button.disabled = True
        self.sync_button.background_color = COLOR_DISABLED_BG
        self.sync_button.color = COLOR_DISABLED_FG
        self.sync_button.text = "SD CARD SAFELY EJECTED"

        self.show_popup("Safe to Remove", "All storage caches flushed.\nYou can now unplug your USB card reader.")

    def scan_and_preview(self):
        self.list_layout.clear_widgets()
        self.all_scanned_items.clear()

        if not has_all_files_access():
            self.status_chip.text = "Storage permission needed"
            self.status_chip.color = COLOR_ERROR_TEXT
            self.sync_button.disabled = True
            self.sync_button.background_color = COLOR_DISABLED_BG
            self.sync_button.color = COLOR_DISABLED_FG
            self.sync_button.text = "GRANT ALL FILES ACCESS"
            self.sync_button.disabled = False
            self.show_popup(
                "Storage Permission Needed",
                "Miyoo Sync needs \"All files access\" to read your saves "
                "on Android 11+.\n\nTap the button below to open Settings, "
                "enable it for Miyoo Sync, then come back and hit Rescan."
            )
            return

        self.miyoo_saves_path, self.miyoo_states_path, self.miyoo_sd_root = find_miyoo_sd_roots()

        if not self.miyoo_sd_root:
            self.status_chip.text = "No SD Card Detected"
            self.status_chip.color = COLOR_ERROR_TEXT
            self.sync_button.disabled = True
            self.sync_button.background_color = COLOR_DISABLED_BG
            self.sync_button.color = COLOR_DISABLED_FG
            self.sync_button.text = "NO SD CARD DETECTED"
            self.show_popup(
                "No SD Card Detected",
                "Checked every mounted volume under /storage for a "
                "Saves/CurrentProfile folder (the Onion OS layout) and "
                "didn't find one.\n\nMake sure the Miyoo's SD card is "
                "connected via USB-OTG and mounted, then hit Rescan."
            )
            return

        vol_name = self.miyoo_sd_root.name
        self.status_chip.text = f"Connected: {vol_name}"
        self.status_chip.color = COLOR_SUCCESS_TEXT

        nova_save_roots, nova_state_roots = find_android_roots()

        nova_files = {}
        for r in nova_save_roots:
            for f in r.rglob("*"):
                if f.is_file() and f.suffix.lower() in SAVE_EXTENSIONS:
                    if f.name not in nova_files or f.stat().st_mtime > nova_files[f.name].stat().st_mtime:
                        nova_files[f.name] = f
        for r in nova_state_roots:
            for f in r.rglob("*"):
                if f.is_file() and classify_file_type(f.name) in ["Save State", "Auto State"]:
                    if f.name not in nova_files or f.stat().st_mtime > nova_files[f.name].stat().st_mtime:
                        nova_files[f.name] = f

        miyoo_files = {}
        if self.miyoo_saves_path:
            for f in self.miyoo_saves_path.rglob("*"):
                if f.is_file() and f.suffix.lower() in SAVE_EXTENSIONS:
                    if f.name not in miyoo_files or f.stat().st_mtime > miyoo_files[f.name].stat().st_mtime:
                        miyoo_files[f.name] = f
        if self.miyoo_states_path:
            for f in self.miyoo_states_path.rglob("*"):
                if f.is_file() and classify_file_type(f.name) in ["Save State", "Auto State"]:
                    if f.name not in miyoo_files or f.stat().st_mtime > miyoo_files[f.name].stat().st_mtime:
                        miyoo_files[f.name] = f

        all_names = sorted(set(nova_files.keys()).union(set(miyoo_files.keys())))
        default_nova_save = nova_save_roots[0] if nova_save_roots else Path("/storage/emulated/0/RetroArch/saves")
        default_nova_state = nova_state_roots[0] if nova_state_roots else Path("/storage/emulated/0/RetroArch/states")

        for name in all_names:
            kind = classify_file_type(name)
            n_file = nova_files.get(name)
            m_file = miyoo_files.get(name)

            m_str, m_ts = format_mtime(m_file)
            n_str, n_ts = format_mtime(n_file)

            direction = "In Sync"
            src, dst = None, None

            if m_file and n_file:
                if abs(m_ts - n_ts) > 2:
                    if m_ts > n_ts:
                        direction = "Miyoo -> Nova"
                        src, dst = m_file, n_file
                    else:
                        direction = "Nova -> Miyoo"
                        src, dst = n_file, m_file
            elif m_file and not n_file:
                direction = "Miyoo -> Nova"
                src = m_file
                dst = (default_nova_save / name) if kind == "Battery Save" else (default_nova_state / name)
            elif n_file and not m_file:
                direction = "Nova -> Miyoo"
                src = n_file
                if kind == "Battery Save" and self.miyoo_saves_path:
                    dst = self.miyoo_saves_path / name
                elif self.miyoo_states_path:
                    dst = self.miyoo_states_path / name

            self.all_scanned_items.append({
                "name": name,
                "kind": kind,
                "m_str": m_str,
                "n_str": n_str,
                "direction": direction,
                "src": src,
                "dst": dst,
                "miyoo_file": m_file,
                "nova_file": n_file
            })

        self.render_filtered_view()

    def render_filtered_view(self):
        self.list_layout.clear_widgets()

        saves_count = sum(1 for i in self.all_scanned_items if i["kind"] == "Battery Save")
        states_count = sum(1 for i in self.all_scanned_items if i["kind"] in ["Save State", "Auto State"])

        self.filter_buttons["ALL"].text = f"All ({len(self.all_scanned_items)})"
        self.filter_buttons["SAVES"].text = f"Saves ({saves_count})"
        self.filter_buttons["STATES"].text = f"States ({states_count})"

        active_count = 0

        for item in self.all_scanned_items:
            kind = item["kind"]
            if self.active_filter == "SAVES" and kind != "Battery Save":
                continue
            if self.active_filter == "STATES" and kind not in ["Save State", "Auto State"]:
                continue

            if item["direction"] in ["Miyoo -> Nova", "Nova -> Miyoo"]:
                active_count += 1

            row = SolidLayout(COLOR_SURFACE_CARD, orientation="horizontal", size_hint_y=None, height=38, padding=[8, 4, 8, 4], spacing=4)
            row.add_widget(Label(text=kind, font_size="10sp", size_hint_x=0.18, color=COLOR_TEXT_MED))
            row.add_widget(Label(text=item["name"], font_size="10sp", size_hint_x=0.38, color=COLOR_TEXT_HIGH, halign="left"))
            row.add_widget(Label(text=item["m_str"], font_size="10sp", size_hint_x=0.18, color=COLOR_TEXT_MED))

            # Direction button that cycles on tap: Miyoo -> Nova -> Skip -> Nova -> Miyoo
            dir_btn = Button(
                text=item["direction"],
                font_size="10sp",
                size_hint_x=0.26,
                background_normal="",
                background_color=COLOR_CONTAINER_ACTIVE if item["direction"] != "In Sync" else COLOR_CONTAINER,
                color=COLOR_TEXT_HIGH
            )
            dir_btn.bind(on_release=lambda inst, it=item: self.toggle_direction(it, inst))
            row.add_widget(dir_btn)

            self.list_layout.add_widget(row)

        self.update_sync_button()

    def toggle_direction(self, item, btn):
        cycle = {
            "In Sync": "Miyoo -> Nova",
            "Miyoo -> Nova": "Nova -> Miyoo",
            "Nova -> Miyoo": "Skip",
            "Skip": "Miyoo -> Nova"
        }
        item["direction"] = cycle.get(item["direction"], "Skip")
        btn.text = item["direction"]
        self.update_sync_button()

    def update_sync_button(self):
        active = [i for i in self.all_scanned_items if i["direction"] in ["Miyoo -> Nova", "Nova -> Miyoo"] and i["src"] and i["dst"]]
        if active:
            self.sync_button.disabled = False
            self.sync_button.background_color = COLOR_PRIMARY
            self.sync_button.color = COLOR_ON_PRIMARY
            self.sync_button.text = f"SYNC {len(active)} ITEM(S) NOW"
        else:
            self.sync_button.disabled = True
            self.sync_button.background_color = COLOR_DISABLED_BG
            self.sync_button.color = COLOR_DISABLED_FG
            self.sync_button.text = "ALL ITEMS IN SYNC"

    def execute_sync(self):
        if not has_all_files_access():
            open_all_files_access_settings()
            return

        active = [i for i in self.all_scanned_items if i["direction"] in ["Miyoo -> Nova", "Nova -> Miyoo"] and i["src"] and i["dst"]]
        if not active:
            return

        nova_save_roots, _ = find_android_roots()
        base_dir = nova_save_roots[0] if nova_save_roots else Path("/storage/emulated/0/RetroArch/saves")
        backup_dir = base_dir / "_unified_backups" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)

        saves_synced = 0
        states_synced = 0

        for item in active:
            src, dst, kind = item["src"], item["dst"], item["kind"]
            if dst.exists():
                shutil.copy2(dst, backup_dir / dst.name)

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

            if kind == "Battery Save":
                saves_synced += 1
            else:
                states_synced += 1

        flush_disk_caches()
        self.show_popup("Sync Complete", f"Successfully synced:\n• {saves_synced} Saves\n• {states_synced} States\n\nBackup created in _unified_backups")
        self.scan_and_preview()


if __name__ == "__main__":
    MiyooSyncApp().run()