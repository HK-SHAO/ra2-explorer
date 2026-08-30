from pathlib import Path

from PyInstaller.utils.hooks import get_package_paths

_, package_dir = get_package_paths("opencc")
share_dir = Path(package_dir) / "clib" / "share" / "opencc"
required_files = (
    "CJK_Compatibility_Ideographs.ocd2",
    "STCharacters.ocd2",
    "STPhrases.ocd2",
    "STPhrases_GeneratedFromRegionalPhrases.ocd2",
    "TSCharacters.ocd2",
    "TSCharactersExt.ocd2",
    "TSPhrases.ocd2",
    "s2t.json",
    "t2s.json",
)
datas = [
    (str(share_dir / name), "opencc/clib/share/opencc")
    for name in required_files
]
