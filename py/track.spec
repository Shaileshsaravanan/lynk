# track.spec

block_cipher = None

a = Analysis(
    ['track.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('python_packages', 'python_packages')
    ],
    hiddenimports=[
        'fastapi',
        'uvicorn',
        'socketio',
        'pywinctl',
        'psutil',
        'platformdirs'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PyObjC', 'Quartz', 'AppKit'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='track',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='track'
)