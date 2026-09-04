# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — gera SinapescREAP.exe (Windows)."""

from PyInstaller.utils.hooks import collect_all

datas = [("assets", "assets"), ("web", "web")]
binaries = []
hiddenimports = [
    "google.oauth2.service_account",
    "googleapiclient",
    "googleapiclient.discovery",
    "googleapiclient.http",
    "qrcode",
    "qrcode.image.pil",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "controle",
    "controle.auditoria",
    "controle.backup",
    "controle.calendario",
    "controle.pendencias",
    "controle.relatorio",
    "controle.defeso",
    "controle.defeso_anexos",
    "controle.defeso_declaracao",
    "controle.defeso_pacote",
    "controle.defeso_relatorio",
    "controle.sync_planilhas",
    "controle.consulta_rgp",
    "controle.consulta_rgp_mpa",
    "controle.consulta_rgp_funcoes",
    "controle.consulta_rgp_funcoes.vencidos",
    "controle.consulta_rgp_funcoes.exportar",
    "controle.consulta_rgp_funcoes.alertas",
    "controle.consulta_rgp_funcoes.fila_inteligente",
    "controle.consulta_rgp_funcoes.importar_arquivo",
    "controle.consulta_rgp_funcoes.editar_lote",
    "webapp.consulta_rgp_ext",
    "pymupdf",
    "fitz",
    "openpyxl",
    "xlrd",
    "drive",
    "drive.client",
    "sheets.defeso_service",
    "sheets.consulta_rgp_service",
    "webview",
    "webapp",
    "webapp.api",
    "webapp.launcher",
    "webapp.paths",
    "webapp.serialize",
]

tmp_ret = collect_all("googleapiclient")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

tmp_webview = collect_all("webview")
datas += tmp_webview[0]
binaries += tmp_webview[1]
hiddenimports += tmp_webview[2]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SinapescREAP",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # janela sem terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)
