[app]
title = Miyoo Sync
package.name = miyoosync
package.domain = org.handheld
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png
version = 1.0.0
requirements = python3,kivy
orientation = landscape
android.wakelock = False
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, MANAGE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 26
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
