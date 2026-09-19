# Miyoo Sync

A touch-friendly bridge for syncing save data between an Android RetroArch
setup and a Miyoo Mini / Miyoo Mini Plus (Onion OS) SD card over USB-OTG.

## What it does

Miyoo Sync scans both storage locations, compares battery saves (`.srm`,
`.sav`) and save states (`.state`, `.state0`–`.state9`, `.state.auto`) by
modification time, and shows you which side is newer for each item. You can
cycle the sync direction per item (`Miyoo -> Nova`, `Nova -> Miyoo`, or
`Skip`) and then sync everything in one tap. A timestamped backup of every
overwritten file is kept under `_unified_backups/` before anything is
replaced.

- **Target platforms:** Android handhelds (Retroid Pocket series, Odin,
  Android phones) running Android 8.0–13+ (API 26–33), connected to a
  Miyoo Mini / Miyoo Mini Plus via USB-OTG.
- **UI:** Python + [Kivy](https://kivy.org/), styled with a Material 3
  (Material You) dark tonal palette.
- **Desktop fallback:** `miyoo_dock.py` — a Tkinter-based standalone version
  for use from a desktop card reader instead of USB-OTG.

## Building the APK

No local Android SDK/NDK setup is required. Pushing to `main` or tagging a
release (`v*`) triggers the GitHub Actions workflow in
`.github/workflows/build_apk.yml`, which uses
[Buildozer](https://github.com/kivy/buildozer) to compile, package, and
upload a signed `.apk` as a build artifact (and attach it to the GitHub
Release when a `v*` tag is pushed).

The first build takes 5–8 minutes while the container downloads the Android
SDK/NDK; the `.apk` then appears under the **Actions** tab for that run, in
the **Artifacts** section.

To build locally instead:

```bash
pip install buildozer
buildozer android debug
```

## Permissions

The app requests `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`, and
`MANAGE_EXTERNAL_STORAGE` in order to read and write RetroArch save
directories and the Miyoo SD card's `Saves/CurrentProfile` structure.

## Disclaimer

This is an unofficial, community tool. It is not affiliated with or endorsed
by the Miyoo, Onion OS, or RetroArch projects. Back up your save data before
syncing — while the app writes a backup of every file it overwrites, you are
responsible for verifying your saves after any sync operation.

## License

MIT — see [LICENSE](LICENSE).
