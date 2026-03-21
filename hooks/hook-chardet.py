from PyInstaller.utils.hooks import collect_all
import glob
import os

datas, binaries, hiddenimports = collect_all('chardet')

# chardet v7+ is compiled with mypyc. The compiled extensions reference a
# top-level mypyc runtime module whose name is a build-specific hash
# (e.g., '0deeb2fec52624e647be__mypyc'). This module lives in the same
# site-packages directory as chardet itself. Discover it dynamically.
import chardet
site_dir = os.path.dirname(os.path.dirname(chardet.__file__))
for ext in ('*.pyd', '*.so'):
    for path in glob.glob(os.path.join(site_dir, '*__mypyc*' + ext[1:])):
        basename = os.path.basename(path)
        mod_name = basename.split('.')[0]
        hiddenimports.append(mod_name)
        binaries.append((path, '.'))
