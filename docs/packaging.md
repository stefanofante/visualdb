# Desktop packages

The desktop build produces an installer for Windows x64 and a disk image
containing a native application for macOS on Apple Silicon. Both include
Python, NiceGUI, SQLite, DuckDB and the Python drivers in the all-drivers extra.
SQL Server connections require a compatible system ODBC driver. SQLCipher is
optional and is not bundled by the standard builds.

## Building a candidate

Push the commit to the `release` branch to build both installers. To rebuild the
current release branch manually, select **Actions → Desktop candidates → Run workflow**
and choose `release`. Development pushes to `master` run source tests for code,
packaging and workflow changes. The Windows and Mac packaging runners execute
the source suite, build a native application and start the frozen binary in
loopback web mode to check its UI routes. Download the two workflow artifacts
for the commit under test and extract the GitHub ZIP wrappers.

| Target | Artifact | Installation |
| --- | --- | --- |
| Windows 10/11 x64 | DBVisual-Windows-x64-Setup.exe | Double-click the installer. It installs for the current user and creates a Start menu entry. The installer includes Microsoft's offline WebView2 runtime and runs it if needed. |
| macOS Apple Silicon | DBVisual-macOS-arm64.dmg | Open the image, drag DBVisual into Applications and open it from there. |

Candidates use no publisher signing identity or Apple notarization. Windows
SmartScreen or macOS Gatekeeper may require a manual decision on a downloaded
candidate. Ordinary build commits only produce candidates. A versioned release commit publishes the tested installers.

For a local build, use 64-bit Python 3.12 on the target platform. On macOS
install the ODBC driver manager with `brew install unixodbc` and verify that
the interpreter reports arm64. Windows needs Inno Setup 6.
From a virtual environment in the repository root run:

```text
python -m pip install ".[dev,all-drivers,packaging]"
python -m pytest
python scripts/build_desktop.py
python scripts/smoke_desktop.py
```

On Windows run `packaging/build-windows.ps1` in PowerShell. It downloads the
x64 standalone WebView2 installer and checks its Microsoft signature. Internet
access is needed on the build machine. On the Mac the disk-image step in the
workflow uses `ditto` and `hdiutil` on the generated app. Both installers are
written under `dist/`.

## Installed-product acceptance

1. Install on Windows 10 x64 and on an Apple Silicon Mac with no system Python.
   Open the application from Start or Applications.
2. Create a SQLite database, save the connection, reopen the application and
   browse its schema. Repeat with an existing database used in production.
3. Save a form and a sheet, edit and delete a row, and confirm that a concurrent
   edit produces a conflict with the local draft still visible.
4. Upload, cancel, save, download and remove an attachment. Check the file
   contents after restarting the application.
5. Export grouped report data to HTML and Excel. Reopen both exports.
6. Install the next build over the existing installation and confirm that saved
   connections, secrets, definitions and attachments remain available in the
   per-user data directory shown in Settings.

## Publish a tagged release

Set the new version in `pyproject.toml` and enter its date and changes in
`CHANGELOG.md`. Give the commit the subject `Release vX.Y.Z.W`, substituting
the actual version. From that commit on `master`, run `git push origin HEAD:release`
to promote it. After both native jobs succeed,
the publishing job checks the dated changelog, the package version and the two
artifacts from that run. It creates the public GitHub release and tag at the
same commit and attaches the installers. A tag ending in `-rc.N` produces a
prerelease. To publish an existing successful build of `release` manually, select
**Actions → Publish desktop release → Run workflow**, choose `release` and enter its tag.
