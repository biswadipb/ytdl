"""Writes the Windows "Details" tab (product name, description, version) that goes inside the .exe.

An .exe with no such details looks anonymous to antivirus programs; one that says who made it and what it is
gets flagged less. Usage: python make_version_info.py <product> <description> <version> <out-file>
"""
import sys

product, description, version, out = sys.argv[1:5]
parts = (version.split(".") + ["0", "0", "0", "0"])[:4]
nums = ", ".join(str(int(p)) if p.isdigit() else "0" for p in parts)
open(out, "w", encoding="utf-8").write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({nums}), prodvers=({nums}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'ytdl (open source, github.com/biswadipb/ytdl)'),
      StringStruct('FileDescription', '{description}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{product}'),
      StringStruct('LegalCopyright', 'GPL-3.0'),
      StringStruct('OriginalFilename', '{product}.exe'),
      StringStruct('ProductName', '{product}'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""")
