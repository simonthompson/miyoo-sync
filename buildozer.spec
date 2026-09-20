[app]
title = Miyoo Sync
package.name = miyoosync
package.domain = org.handheld
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
icon.filename = %(source.dir)s/icon.png
icon.adaptive_foreground.filename = %(source.dir)s/icon_foreground.png
icon.adaptive_background.filename = %(source.dir)s/icon_background.png
presplash.filename = %(source.dir)s/presplash.png
version = 1.0.0
requirements = python3,kivy
orientation = landscape
android.wakelock = False
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, MANAGE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 26
# Single-arch build. python-for-android has a known upstream bug where
# building multiple archs in one run reuses a shared venv directory for
# the pure-Python dependency install stage, corrupting pip on the second
# arch ("ImportError: cannot import name 'BuildDependencyInstallError'").
# arm64-v8a alone covers virtually all modern Android devices (including
# the Retroid Pocket line), so this sidesteps the bug entirely.
android.archs = arm64-v8a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
