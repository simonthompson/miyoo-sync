import os
import shutil
import datetime
import traceback
from pathlib import Path

from kivy.app import App
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle, RoundedRectangle

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
COLOR_SURFACE_CARD = (0.14, 0.15, 0.17, 1.0) # #24262b
COLOR_PRIMARY = (0.66, 0.78, 0.98, 1.0)      # #a8c7fa
COLOR_ON_PRIMARY = (0.02, 0.20, 0.35, 1.0)   # #063259
COLOR_CONTAINER = (0.20, 0.22, 0.25, 1.0)    # #333840
COLOR_CONTAINER_ACTIVE = (0.29, 0.38, 0.48, 1.0)
COLOR_TEXT_HIGH = (0.89, 0.89, 0.90, 1.0)    # #e2e2e6
COLOR_TEXT_MED = (0.64, 0.66, 0.69, 1.0)     # #a3a8b0
COLOR_SUCCESS = (0.09, 0.24, 0.16, 1.0)      # #173d29
COLOR_SUCCESS_TEXT = (0.73, 0.95, 0.78, 1.0)
COLOR_WARN = (0.32, 0.26, 0.09, 1.0)
COLOR_WARN_TEXT = (0.97, 0.85, 0.55, 1.0)
COLOR_ERROR = (0.32, 0.13, 0.13, 1.0)        # #521f1f
COLOR_ERROR_TEXT = (0.96, 0.74, 0.73, 1.0)
COLOR_DISABLED_BG = (0.15, 0.16, 0.18, 1.0)
COLOR_DISABLED_FG = (0.38, 0.40, 0.44, 1.0)

SAVE_EXTENSIONS = {".srm", ".sav"}
BASE_STATE_EXTS = {".state"} | {f".state{i}" for i in range(10)}

ACTIONABLE_DIRECTIONS = {"Miyoo -> Nova", "Nova -> Miyoo"}
DIRECTION_ARROWS = {
    "Miyoo -> Nova": "\u2192 Nova",
    "Nova -> Miyoo": "\u2192 Miyoo",
    "In Sync": "= Synced",
    "Skip": "\u29b8 Skip",
}
SORT_PRIORITY = {"Miyoo -> Nova": 0, "Nova -> Miyoo": 0, "Skip": 1, "In Sync": 2}


def classify_file_type(name: str):
    lower = name.lower()
    if lower.endswith(".state.auto") or lower.endswith(".state.png"):
        return "Auto State"
    if any(lower.endswith(ext) for ext in SAVE_EXTENSIONS):
        return "Battery Save"
    if Path(lower).suffix in BASE_STATE_EXTS or lower.endswith(".state"):
        return "Save State"
    return "Other"


def base_name(filename: str) -> str:
    """Strip the save/state suffix to get the underlying game/content name,
    e.g. 'Zelda.state3' and 'Zelda.srm' both -> 'Zelda'. Used to tell
    whether a game has ANY presence on a device at all, regardless of
    which specific save/state file or slot we're looking at."""
    lower = filename.lower()
    for ext in sorted(SAVE_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return filename[: -len(ext)]
    if lower.endswith(".state.auto"):
        return filename[: -len(".state.auto")]
    for i in range(10):
        suf = f".state{i}"
        if lower.endswith(suf):
            return filename[: -len(suf)]
    if lower.endswith(".state"):
        return filename[: -len(".state")]
    return filename


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
    hardcoded path."""
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


class RoundedBG:
    """Mixin that draws a rounded-rect background behind a widget, in place
    of Kivy's default flat rectangle. Call _init_rounded_bg() after the
    normal widget __init__."""

    def _init_rounded_bg(self, color, radius=14):
        self._bg_radius = radius
        with self.canvas.before:
            self._bg_color_instr = Color(*color)
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[radius])
        self.bind(pos=self._update_rounded_bg, size=self._update_rounded_bg)

    def _update_rounded_bg(self, *_args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def set_rounded_bg_color(self, color):
        self._bg_color_instr.rgba = color


class RoundedButton(RoundedBG, Button):
    def __init__(self, bg_color=COLOR_CONTAINER, radius=14, **kwargs):
        Button.__init__(self, **kwargs)
        self.background_color = (0, 0, 0, 0)
        self.background_normal = ""
        self.background_down = ""
        self._init_rounded_bg(bg_color, radius)


class RoundedBox(RoundedBG, BoxLayout):
    def __init__(self, bg_color, radius=14, **kwargs):
        BoxLayout.__init__(self, **kwargs)
        self._init_rounded_bg(bg_color, radius)


class SolidLayout(BoxLayout):
    """Flat (non-rounded) background box, used for full-width surfaces like
    the top app bar where rounding would look out of place."""
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
        self.miyoo_profile_dir = None

        self.active_filter = "ALL"
        self.all_scanned_items = []

        # Root vertical layout
        root = BoxLayout(orientation="vertical", padding=[14, 12, 14, 12], spacing=10)

        # 1. Top App Bar
        app_bar = SolidLayout(COLOR_SURFACE, orientation="horizontal", size_hint_y=None, height=52, padding=[4, 6, 4, 6], spacing=10)

        title_label = Label(text="[b]Miyoo Sync[/b]", markup=True, font_size="18sp", color=COLOR_TEXT_HIGH, size_hint_x=None, width=104, halign="left", valign="middle")
        title_label.bind(size=title_label.setter('text_size'))
        app_bar.add_widget(title_label)

        # Status pill: colored dot + text, Material 3 "assist chip" style.
        # size_hint_x=1 (rather than a fixed fraction) so it claims whatever
        # space the fixed-width title/buttons around it don't use — keeps
        # the status text readable across different screen widths.
        self.status_pill = RoundedBox(COLOR_SURFACE_CARD, radius=16, orientation="horizontal", padding=[10, 0, 10, 0], spacing=6, size_hint_x=1)
        self.status_dot = RoundedBox(COLOR_TEXT_MED, radius=5, size_hint=(None, None), size=(10, 10), pos_hint={"center_y": 0.5})
        self.status_pill.add_widget(self.status_dot)
        self.status_label = Label(text="Scanning USB-OTG...", font_size="12sp", color=COLOR_TEXT_MED, halign="left", valign="middle", shorten=True)
        self.status_label.bind(size=self.status_label.setter('text_size'))
        self.status_pill.add_widget(self.status_label)
        app_bar.add_widget(self.status_pill)

        rescan_btn = RoundedButton(
            bg_color=COLOR_CONTAINER, radius=14,
            text="Rescan", font_size="12sp", size_hint_x=None, width=68,
            color=COLOR_TEXT_HIGH
        )
        rescan_btn.bind(on_release=lambda x: self.scan_and_preview())
        app_bar.add_widget(rescan_btn)

        eject_btn = RoundedButton(
            bg_color=COLOR_ERROR, radius=14,
            text="Eject", font_size="12sp", size_hint_x=None, width=58,
            color=COLOR_ERROR_TEXT
        )
        eject_btn.bind(on_release=lambda x: self.safely_eject())
        app_bar.add_widget(eject_btn)

        root.add_widget(app_bar)

        # 2. Filter Bar (segmented control style)
        filter_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=38, spacing=6)
        self.filter_buttons = {}
        for key, label_text in [("ALL", "All"), ("SAVES", "Battery Saves"), ("STATES", "Save States")]:
            btn = RoundedButton(
                bg_color=COLOR_CONTAINER_ACTIVE if key == "ALL" else COLOR_CONTAINER,
                radius=18,
                text=label_text, font_size="12sp", color=COLOR_TEXT_HIGH
            )
            btn.bind(on_release=lambda inst, k=key: self.set_filter(k))
            self.filter_buttons[key] = btn
            filter_bar.add_widget(btn)
        root.add_widget(filter_bar)

        # 3. Table Header (lightweight, no card fill)
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=26, padding=[12, 0, 12, 0])
        header.add_widget(Label(text="TYPE", font_size="10sp", size_hint_x=0.18, color=COLOR_TEXT_MED))
        header.add_widget(Label(text="ITEM / GAME", font_size="10sp", size_hint_x=0.36, color=COLOR_TEXT_MED, halign="left"))
        header.add_widget(Label(text="MIYOO", font_size="10sp", size_hint_x=0.18, color=COLOR_TEXT_MED))
        header.add_widget(Label(text="DIRECTION", font_size="10sp", size_hint_x=0.28, color=COLOR_TEXT_MED))
        root.add_widget(header)

        # 4. Scrollable Item List
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.list_layout = GridLayout(cols=1, spacing=6, size_hint_y=None)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

        # 5. Bottom Sync Action Button (full-width filled pill)
        self.sync_button = RoundedButton(
            bg_color=COLOR_DISABLED_BG, radius=24,
            text="NO ITEMS TO SYNC", font_size="14sp", bold=True,
            size_hint_y=None, height=50,
            color=COLOR_DISABLED_FG, disabled=True
        )
        self.sync_button.bind(on_release=lambda x: self.execute_sync())
        root.add_widget(self.sync_button)

        self.scan_and_preview()
        return root

    # ---- status pill helper -------------------------------------------------

    def set_status(self, text, tone="info"):
        tone_colors = {
            "info": (COLOR_TEXT_MED, COLOR_TEXT_MED),
            "success": (COLOR_SUCCESS_TEXT, COLOR_SUCCESS_TEXT),
            "warn": (COLOR_WARN_TEXT, COLOR_WARN_TEXT),
            "error": (COLOR_ERROR_TEXT, COLOR_ERROR_TEXT),
        }
        dot_color, text_color = tone_colors.get(tone, tone_colors["info"])
        self.status_label.text = text
        self.status_label.color = text_color
        self.status_dot.set_rounded_bg_color(dot_color)

    def set_filter(self, mode):
        self.active_filter = mode
        for k, btn in self.filter_buttons.items():
            btn.set_rounded_bg_color(COLOR_CONTAINER_ACTIVE if k == mode else COLOR_CONTAINER)
        self.render_filtered_view()

    def show_popup(self, title, message, action_text=None, action_callback=None):
        """Popup with a message, and optionally one prominent action button
        (e.g. 'Grant Access') in addition to the close button — so the fix
        for a problem is right there in the dialog instead of a separate
        control the person has to go find afterward."""
        outer = BoxLayout(orientation="vertical", spacing=12, padding=[4, 4, 4, 4])

        content = Label(text=message, font_size="13sp", color=COLOR_TEXT_HIGH, halign="left", valign="top")
        content.bind(size=lambda inst, val: setattr(inst, 'text_size', (val[0] - 20, None)))
        outer.add_widget(content)

        popup = Popup(title=title, content=outer, size_hint=(0.85, 0.5))

        button_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=48, spacing=8)
        if action_text and action_callback:
            def _run_action(*_a):
                popup.dismiss()
                action_callback()
            action_btn = RoundedButton(
                bg_color=COLOR_PRIMARY, radius=14,
                text=action_text, font_size="14sp", bold=True,
                color=COLOR_ON_PRIMARY
            )
            action_btn.bind(on_release=_run_action)
            button_row.add_widget(action_btn)

        close_btn = RoundedButton(
            bg_color=COLOR_CONTAINER, radius=14,
            text="Close" if (action_text and action_callback) else "OK",
            font_size="13sp", color=COLOR_TEXT_HIGH,
            size_hint_x=0.4 if (action_text and action_callback) else 1
        )
        close_btn.bind(on_release=lambda *_a: popup.dismiss())
        button_row.add_widget(close_btn)

        outer.add_widget(button_row)
        popup.open()

    def safely_eject(self):
        if not self.miyoo_sd_root:
            self.show_popup("Eject", "No Miyoo SD Card is currently connected.")
            return

        flush_disk_caches()
        self.miyoo_saves_path = None
        self.miyoo_states_path = None
        self.miyoo_sd_root = None
        self.miyoo_profile_dir = None
        self.all_scanned_items.clear()
        self.list_layout.clear_widgets()

        self.set_status("Safely ejected", "info")

        self.sync_button.disabled = True
        self.sync_button.set_rounded_bg_color(COLOR_DISABLED_BG)
        self.sync_button.color = COLOR_DISABLED_FG
        self.sync_button.text = "SD CARD SAFELY EJECTED"

        self.show_popup("Safe to Remove", "All storage caches flushed.\nYou can now unplug your USB card reader.")

    def scan_and_preview(self):
        self.list_layout.clear_widgets()
        self.all_scanned_items.clear()

        if not has_all_files_access():
            self.set_status("Storage permission needed", "error")
            self.sync_button.disabled = False
            self.sync_button.set_rounded_bg_color(COLOR_WARN)
            self.sync_button.color = COLOR_WARN_TEXT
            self.sync_button.text = "GRANT ALL FILES ACCESS"
            self.show_popup(
                "Storage Permission Needed",
                "Miyoo Sync needs \"All files access\" to read your saves "
                "on Android 11+.\n\nTap Grant Access below to open Settings, "
                "enable it for Miyoo Sync, then come back and hit Rescan.",
                action_text="Grant Access",
                action_callback=open_all_files_access_settings
            )
            return

        try:
            self._do_scan()
        except Exception as exc:
            self.set_status("Scan failed", "error")
            self.show_popup(
                "Scan Error",
                f"Something went wrong while scanning:\n\n{exc}\n\n"
                "Tap Rescan to try again."
            )
            traceback.print_exc()

    def _do_scan(self):
        self.miyoo_saves_path, self.miyoo_states_path, self.miyoo_sd_root = find_miyoo_sd_roots()

        if not self.miyoo_sd_root:
            self.set_status("No SD card detected", "error")
            self.sync_button.disabled = True
            self.sync_button.set_rounded_bg_color(COLOR_DISABLED_BG)
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
        self.set_status(f"Connected: {vol_name}", "success")

        # Even if the "saves" or "states" subfolder doesn't exist yet on the
        # card (e.g. no save state has ever been made in Onion OS), we still
        # know where it *should* go — execute_sync() creates missing parent
        # folders on write. Without this fallback, items with no existing
        # Miyoo-side folder silently had no sync destination and just sat
        # there doing nothing when synced.
        self.miyoo_profile_dir = self.miyoo_sd_root / "Saves" / "CurrentProfile"
        fallback_miyoo_saves = self.miyoo_profile_dir / "saves"
        fallback_miyoo_states = self.miyoo_profile_dir / "states"

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
        # Track which core-subfolder (if any) each game already lives under
        # on the Miyoo card, e.g. 'gpsp' for a GBA save under
        # states/gpsp/Game.state0 — Onion OS nests saves/states by core,
        # unlike Android RetroArch's typically-flat layout. We use this
        # both to write new files into the RIGHT subfolder (previously
        # they were flattened into the root and Onion OS never found them)
        # and to tell whether a game has ANY presence on the Miyoo at all.
        miyoo_core_by_base = {}
        if self.miyoo_saves_path:
            for f in self.miyoo_saves_path.rglob("*"):
                if f.is_file() and f.suffix.lower() in SAVE_EXTENSIONS:
                    if f.name not in miyoo_files or f.stat().st_mtime > miyoo_files[f.name].stat().st_mtime:
                        miyoo_files[f.name] = f
                    rel_dir = f.parent.relative_to(self.miyoo_saves_path)
                    miyoo_core_by_base.setdefault(base_name(f.name), str(rel_dir))
        if self.miyoo_states_path:
            for f in self.miyoo_states_path.rglob("*"):
                if f.is_file() and classify_file_type(f.name) in ["Save State", "Auto State"]:
                    if f.name not in miyoo_files or f.stat().st_mtime > miyoo_files[f.name].stat().st_mtime:
                        miyoo_files[f.name] = f
                    rel_dir = f.parent.relative_to(self.miyoo_states_path)
                    miyoo_core_by_base.setdefault(base_name(f.name), str(rel_dir))

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
                src = n_file
                base = base_name(name)
                core_subdir = miyoo_core_by_base.get(base)
                target_root = (self.miyoo_saves_path if kind == "Battery Save" else self.miyoo_states_path) \
                    or (fallback_miyoo_saves if kind == "Battery Save" else fallback_miyoo_states)
                if core_subdir and core_subdir != ".":
                    dst = target_root / core_subdir / name
                else:
                    dst = target_root / name
                # Only offer this as an actionable push if the game already
                # has SOME presence on the Miyoo (any core, any slot) --
                # otherwise it's very likely a system the Miyoo can't even
                # run (e.g. a PS1/N64 save from a more capable device), and
                # auto-pushing it there just clutters the card with saves
                # for a game that will never load. Defaults to Skip, but
                # still tappable to force it if you really want to.
                direction = "Nova -> Miyoo" if base in miyoo_core_by_base else "Skip"

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

        # Surface anything out of sync first so it's not buried below a long
        # alphabetical list of items that are already fine.
        self.all_scanned_items.sort(key=lambda i: (SORT_PRIORITY.get(i["direction"], 0), i["name"].lower()))

        self.render_filtered_view()

    def render_filtered_view(self):
        self.list_layout.clear_widgets()

        saves_count = sum(1 for i in self.all_scanned_items if i["kind"] == "Battery Save")
        states_count = sum(1 for i in self.all_scanned_items if i["kind"] in ["Save State", "Auto State"])

        self.filter_buttons["ALL"].text = f"All ({len(self.all_scanned_items)})"
        self.filter_buttons["SAVES"].text = f"Saves ({saves_count})"
        self.filter_buttons["STATES"].text = f"States ({states_count})"

        for item in self.all_scanned_items:
            kind = item["kind"]
            if self.active_filter == "SAVES" and kind != "Battery Save":
                continue
            if self.active_filter == "STATES" and kind not in ["Save State", "Auto State"]:
                continue

            row = RoundedBox(COLOR_SURFACE_CARD, radius=10, orientation="horizontal", size_hint_y=None, height=42, padding=[10, 4, 10, 4], spacing=4)
            row.add_widget(Label(text=kind, font_size="10sp", size_hint_x=0.18, color=COLOR_TEXT_MED))
            name_label = Label(text=item["name"], font_size="10sp", size_hint_x=0.36, color=COLOR_TEXT_HIGH, halign="left", valign="middle", shorten=True)
            name_label.bind(size=name_label.setter('text_size'))
            row.add_widget(name_label)
            row.add_widget(Label(text=item["m_str"], font_size="10sp", size_hint_x=0.18, color=COLOR_TEXT_MED))

            # Direction chip that cycles on tap: Miyoo -> Nova -> Skip -> Nova -> Miyoo
            is_actionable = item["direction"] in ACTIONABLE_DIRECTIONS
            dir_btn = RoundedButton(
                bg_color=COLOR_CONTAINER_ACTIVE if is_actionable else COLOR_CONTAINER,
                radius=14,
                text=DIRECTION_ARROWS.get(item["direction"], item["direction"]),
                font_size="10sp",
                size_hint_x=0.28,
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
        btn.text = DIRECTION_ARROWS.get(item["direction"], item["direction"])
        btn.set_rounded_bg_color(COLOR_CONTAINER_ACTIVE if item["direction"] in ACTIONABLE_DIRECTIONS else COLOR_CONTAINER)
        self.update_sync_button()

    def _active_items(self):
        return [i for i in self.all_scanned_items if i["direction"] in ACTIONABLE_DIRECTIONS and i["src"] and i["dst"]]

    def update_sync_button(self):
        active = self._active_items()
        if active:
            self.sync_button.disabled = False
            self.sync_button.set_rounded_bg_color(COLOR_PRIMARY)
            self.sync_button.color = COLOR_ON_PRIMARY
            self.sync_button.text = f"SYNC {len(active)} ITEM(S) NOW"
        else:
            self.sync_button.disabled = True
            self.sync_button.set_rounded_bg_color(COLOR_DISABLED_BG)
            self.sync_button.color = COLOR_DISABLED_FG
            self.sync_button.text = "ALL ITEMS IN SYNC"

    def execute_sync(self):
        if not has_all_files_access():
            open_all_files_access_settings()
            return

        active = self._active_items()
        if not active:
            return

        # Give immediate visual feedback the instant the button is tapped.
        # The actual file copying is fast but blocks the UI thread while it
        # runs, so without this the button press could look like it did
        # nothing at all for however long the copy takes. Deferring the
        # real work to the next frame (Clock.schedule_once) lets Kivy
        # actually paint this state before the blocking work starts.
        self.sync_button.disabled = True
        self.sync_button.set_rounded_bg_color(COLOR_CONTAINER_ACTIVE)
        self.sync_button.color = COLOR_TEXT_HIGH
        self.sync_button.text = f"SYNCING {len(active)} ITEM(S)..."
        Clock.schedule_once(lambda _dt: self._run_sync(active), 0)

    def _run_sync(self, active):
        try:
            self._do_sync(active)
        except Exception as exc:
            self.show_popup(
                "Sync Error",
                f"Sync stopped because of an unexpected error:\n\n{exc}\n\n"
                "Nothing past this point was copied. Check that the Miyoo's "
                "SD card is still writable (some USB-OTG card readers need "
                "\"All files access\" AND to be reconnected after granting "
                "it), then hit Rescan and try again."
            )
            traceback.print_exc()
            self.update_sync_button()

    def _do_sync(self, active):
        nova_save_roots, _ = find_android_roots()
        base_dir = nova_save_roots[0] if nova_save_roots else Path("/storage/emulated/0/RetroArch/saves")
        backup_dir = base_dir / "_unified_backups" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)

        saves_synced = 0
        states_synced = 0
        failures = []

        for item in active:
            src, dst, kind = item["src"], item["dst"], item["kind"]
            try:
                if dst.exists():
                    shutil.copy2(dst, backup_dir / dst.name)

                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

                if kind == "Battery Save":
                    saves_synced += 1
                else:
                    states_synced += 1
            except Exception as item_exc:
                # Keep going on the rest of the batch rather than aborting
                # everything because one file couldn't be written — but make
                # sure the failure is actually visible instead of silent.
                failures.append(f"{item['name']}: {item_exc}")

        flush_disk_caches()

        summary = f"Successfully synced:\n\u2022 {saves_synced} Saves\n\u2022 {states_synced} States"
        if saves_synced or states_synced:
            summary += "\n\nBackup created in _unified_backups"
        if failures:
            shown = "\n".join(failures[:5])
            more = f"\n...and {len(failures) - 5} more" if len(failures) > 5 else ""
            summary += f"\n\n{len(failures)} item(s) failed:\n{shown}{more}"
            self.show_popup("Sync Finished With Errors", summary)
        else:
            self.show_popup("Sync Complete", summary)

        self.scan_and_preview()


if __name__ == "__main__":
    MiyooSyncApp().run()
