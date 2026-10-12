import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def find_iscc() -> str:
    """Finds the Inno Setup Compiler executable."""
    candidates = [
        os.path.expandvars(r"%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        os.path.expandvars(r"%ProgramFiles%\Inno Setup 6\ISCC.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    
    # Try finding via where/which
    try:
        out = subprocess.check_output(["where", "ISCC.exe"], text=True, stderr=subprocess.DEVNULL).strip()
        if out and os.path.isfile(out.splitlines()[0]):
            return out.splitlines()[0]
    except Exception:
        pass
    return ""

def ensure_assets():
    """Ensures icons exist before compiling."""
    ico_path = BASE_DIR / "resources" / "ripsync.ico"
    png_path = BASE_DIR / "resources" / "ripsync.png"
    if not ico_path.is_file():
        print("[1/5] Generating application icons...")
        from scripts.generate_assets import generate_ripsync_icon
        generate_ripsync_icon(str(ico_path), str(png_path))
    else:
        print("[1/5] Icons already exist.")

def build_pyinstaller():
    """Runs PyInstaller on ripsync.spec."""
    print("[2/5] Running PyInstaller build...")
    spec_path = BASE_DIR / "ripsync.spec"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec_path)
    ]
    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    if res.returncode != 0:
        print("[ERROR] PyInstaller build failed!")
        sys.exit(res.returncode)

    exe_file = BASE_DIR / "dist" / "RipSync" / "RipSync.exe"
    if not exe_file.is_file():
        print(f"[ERROR] Expected output executable not found: {exe_file}")
        sys.exit(1)

    size_mb = exe_file.stat().st_size / (1024 * 1024)
    print(f"[SUCCESS] Standalone binary compiled: {exe_file} ({size_mb:.2f} MB)")

def create_portable_zip():
    """Zips the dist/RipSync directory into RipSync-Portable.zip."""
    print("[3/5] Creating Portable ZIP archive...")
    src_dir = BASE_DIR / "dist" / "RipSync"
    zip_dest = BASE_DIR / "dist" / "RipSync-Portable.zip"

    # Also touch a portable.txt inside a portable marker if desired
    portable_marker = src_dir / "portable.txt"
    try:
        portable_marker.write_text("portable_mode=true\n", encoding="utf-8")
    except Exception:
        pass

    with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src_dir):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(src_dir.parent)
                zf.write(full_path, rel_path)

    # Remove portable.txt from dist/RipSync so the installed version defaults to %APPDATA%
    try:
        portable_marker.unlink()
    except Exception:
        pass

    size_mb = zip_dest.stat().st_size / (1024 * 1024)
    print(f"[SUCCESS] Portable package created: {zip_dest} ({size_mb:.2f} MB)")

def build_inno_installer(require_installer: bool = False):
    """Compiles the Inno Setup installer."""
    print("[4/5] Checking for Inno Setup compiler...")
    iscc = find_iscc()
    if not iscc:
        msg = "Inno Setup compiler (ISCC.exe) not found. Skipping Setup.exe creation."
        if require_installer or os.environ.get("CI") == "true":
            print(f"[ERROR] {msg}")
            sys.exit(1)
        print(f"[WARNING] {msg}")
        return

    print(f"Using Inno Setup: {iscc}")
    iss_file = BASE_DIR / "installer" / "ripsync_setup.iss"
    cmd = [iscc, str(iss_file)]
    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    if res.returncode != 0:
        print("[ERROR] Inno Setup compilation failed!")
        sys.exit(res.returncode)

    setup_file = BASE_DIR / "dist" / "RipSync-Setup.exe"
    if setup_file.is_file():
        size_mb = setup_file.stat().st_size / (1024 * 1024)
        print(f"[SUCCESS] Windows Installer created: {setup_file} ({size_mb:.2f} MB)")
    else:
        print("[ERROR] Setup file not found after compilation.")
        if require_installer or os.environ.get("CI") == "true":
            sys.exit(1)

def main():
    require_installer = "--require-installer" in sys.argv
    print("=" * 60)
    print("RipSync - Automated Windows Standalone & Installer Builder")
    print("=" * 60)
    ensure_assets()
    build_pyinstaller()
    create_portable_zip()
    build_inno_installer(require_installer=require_installer)
    print("=" * 60)
    print("[5/5] All builds completed successfully! Check the 'dist' folder:")
    dist_dir = BASE_DIR / "dist"
    for item in dist_dir.iterdir():
        if item.is_file():
            print(f"  -> {item.name} ({item.stat().st_size / (1024*1024):.2f} MB)")
        elif item.is_dir():
            print(f"  -> [DIR] {item.name}")
    print("=" * 60)

if __name__ == "__main__":
    main()

