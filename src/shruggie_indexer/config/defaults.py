"""Compiled default configuration values for shruggie-indexer.

These defaults reproduce the behavioral intent of the original
``$global:MetadataFileParser`` object and related hardcoded values, while
extending them for cross-platform coverage (DEV-10) and correcting known
issues.

The tool MUST operate correctly using only compiled defaults — no
configuration file is required.

Source references:
    - MakeIndex(MetadataFileParser).ps1  (regex patterns, extension groups)
    - Spec §7.2-7.5                       (default values, porting guidance)
"""

from __future__ import annotations

import re

from shruggie_indexer.config.types import MetadataTypeAttributes

__all__ = [
    "DEFAULT_EXIFTOOL_ARGS",
    "DEFAULT_EXIFTOOL_EXCLUDE_EXTENSIONS",
    "DEFAULT_EXIFTOOL_EXCLUDE_KEYS",
    "DEFAULT_EXTENSION_GROUPS",
    "DEFAULT_EXTENSION_VALIDATION_PATTERN",
    "DEFAULT_FILESYSTEM_EXCLUDES",
    "DEFAULT_FILESYSTEM_EXCLUDE_GLOBS",
    "DEFAULT_METADATA_ATTRIBUTES",
    "DEFAULT_METADATA_EXCLUDE_PATTERNS",
    "DEFAULT_METADATA_IDENTIFY",
    "DEFAULT_SCALARS",
]


# ---------------------------------------------------------------------------
# Scalar defaults (§7.2)
# ---------------------------------------------------------------------------

DEFAULT_SCALARS: dict[str, object] = {
    "recursive": True,
    "id_algorithm": "md5",
    "compute_sha512": False,
    "output_stdout": True,
    "output_file": None,
    "output_inplace": False,
    "extract_exif": False,
    "meta_merge": False,
    "meta_merge_delete": False,
    "rename": False,
    "dry_run": False,
}

# ---------------------------------------------------------------------------
# Extension validation pattern (§7.2)
# ---------------------------------------------------------------------------

DEFAULT_EXTENSION_VALIDATION_PATTERN: str = (
    r"^(([a-z0-9]){1,2}|([a-z0-9])([a-z0-9\-]){1,12}([a-z0-9]))$"
)

# ---------------------------------------------------------------------------
# Filesystem exclusion defaults (§7.2, DEV-10)
# ---------------------------------------------------------------------------

DEFAULT_FILESYSTEM_EXCLUDES: frozenset[str] = frozenset({
    # Windows
    "$recycle.bin",
    "system volume information",
    "desktop.ini",
    "thumbs.db",
    # macOS
    ".ds_store",
    ".spotlight-v100",
    ".trashes",
    ".fseventsd",
    ".temporaryitems",
    ".documentrevisions-v100",
    # Version control
    ".git",
})

DEFAULT_FILESYSTEM_EXCLUDE_GLOBS: tuple[str, ...] = (
    # Linux
    ".trash-*",
)

# ---------------------------------------------------------------------------
# Exiftool defaults (§7.2, §7.4)
# ---------------------------------------------------------------------------

DEFAULT_EXIFTOOL_EXCLUDE_EXTENSIONS: frozenset[str] = frozenset({
    "csv",
    "htm",
    "html",
    "json",
    "tsv",
    "xml",
})

DEFAULT_EXIFTOOL_EXCLUDE_KEYS: frozenset[str] = frozenset({
    # Original v1 jq deletion list
    "ExifToolVersion",
    "FileSequence",
    "NewGUID",
    "Directory",
    "FileName",
    "FilePath",
    "BaseName",
    "FilePermissions",
    # Absolute path exposure
    "SourceFile",
    # Redundant — captured in IndexEntry size/timestamps objects
    "FileSize",
    "FileModifyDate",
    "FileAccessDate",
    "FileCreateDate",
    # OS-specific filesystem attributes (not embedded metadata)
    "FileAttributes",
    "FileDeviceNumber",
    "FileInodeNumber",
    "FileHardLinks",
    "FileUserID",
    "FileGroupID",
    "FileDeviceID",
    "FileBlockSize",
    "FileBlockCount",
    # ExifTool operational metadata
    "Now",
    "ProcessingTime",
    "Error",
})
"""Default set of exiftool output keys to exclude.

Keys are matched by their base name (the portion after the last ``:``)
to handle group-prefixed output from ``-G`` flags.

Configurable via ``exiftool.exclude_keys`` (replace) or
``exiftool.exclude_keys_append`` (extend) in TOML configuration.
"""

DEFAULT_EXIFTOOL_ARGS: tuple[str, ...] = (
    "-extractEmbedded3",
    "-scanForXMP",
    "-unknown2",
    "-json",
    "-G3:1",
    "-struct",
    "-ignoreMinorErrors",
    "-charset",
    "filename=utf8",
    "-api",
    "requestall=3",
    "-api",
    "largefilesupport=1",
    "--",
)

# ---------------------------------------------------------------------------
# BCP 47 language-code alternation (shared by JsonMetadata and Subtitles)
# ---------------------------------------------------------------------------

# This is the exact set of language codes from the original
# MakeIndex(MetadataFileParser).ps1, used in both JSON subtitle and
# non-JSON subtitle pattern matching.  The alternation MUST be ported
# character-for-character to avoid missing subtitle files.
_BCP47_ALTERNATION: str = (
    "aa|af|sq|gsw-fr|ase|am|ar|arq|abv|arz|acm|ajp|afb-kw|apc|ayl|ary|acx|"
    "afb-qa|ar-sa|ar-sy|aeb|ar-ae|ar-ye|arp|hy|as|az|az-cyrl|az-latn|ba|be|bn|"
    "bn-in|bs|bs-cyrl|bzs|br|br-fr|bg|my|ca|tzm|tzm-arab-ma|tzm-dz|tzm-tfng|"
    "tzm-tfng-ma|ckb|ckb-iq|chr|zh|yue|yue-hk|cmn|cmn-hans|cmn-hans-cn|"
    "cmn-hans-hk|cmn-hans-mo|cmn-hans-my|cmn-hans-sg|cmn-hans-tw|cmn-tw|"
    "cmn-hant|cmn-hant-cn|cmn-hant-hk|cmn-hant-mo|cmn-hant-my|cmn-hant-sg|"
    "cmn-hant-tw|nan|zh-hans|zh-hans-cn|zh-hans-hk|zh-hans-mo|zh-hans-my|"
    "zh-hans-sg|zh-hans-tw|zh-hant|zh-hant-cn|zh-hant-hk|zh-hant-mo|"
    "zh-hant-my|zh-hant-sg|zh-hant-tw|com|co|co-fr|hr|hr-ba|quz|cs|da|prs|dv|"
    "nl|dz|bin|en|en-au|en-bz|en-ca|en-029|en-hk|en-in|en-id|en-ie|en-jm|"
    "en-my|en-nz|en-ph|en-sg|en-za|en-se|en-tt|en-ae|en-gb|en-us|en-zw|et|eu|"
    "fo|fil|fi|nl-be|fr|fr-be|fr-cm|fr-ca|fr-029|fr-ci|fr-ht|fr-lu|fr-ml|"
    "fr-mc|fr-ma|fr-re|fr-sn|fr-ch|fr-cd|ff|ff-latn|ff-latn-ng|ff-latn-sn|"
    "ff-ng|gl|ka|de|de-at|de-li|de-lu|gsw|de-ch|el|gn|gu|ha|ha-latn|ha-latn-ng|"
    "haw|he|hi|hu|ibb|is|ig|id|iu|iu-cans|ga|it|it-ch|ja|ja-jp|quc|kl|kn|kr|"
    "kr-ng|ks|ks-deva-in|kk|km|rw|kok|ko|ky|lad|lo|la|la-va|lv|ln|lt|dsb|lb|"
    "mk|ms-bn|ms-my|ms|ml|mt|mni|mni-beng-in|mi|arn|mr|fit|moh|mn|mn-cn|"
    "mn-mong|mn-mong-cn|nv|ne|ne-in|no|nb|nn|oc|or|om|pap|pap-029|ps|fa|pl|"
    "pt-br|pt|pa|pa-arab|qu|qu-bo|qu-ec|qu-pe|ro|ro-md|rm|ru|ru-md|aec|sah|smi|"
    "smn|smj|smj-no|se|se-fi|se-no|se-se|sms|sma|sma-no|sm|sa|gd|sr|sr-cyrl|"
    "sr-ba|sr-cyrl-me|sr-latn|sr-latn-ba|sr-me|sd|sd-arab|sd-in|si|sk|sl|so|st|"
    "nso|es-ar|es-bo|es|es-cl|es-co|es-cr|es-cu|es-do|es-ec|es-sv|es-gt|es-hn|"
    "es-419|es-mx|es-ni|es-pa|es-py|es-pe|es-pr|es-us|es-uy|es-ve|sw|sw-ke|sv|"
    "sv-fi|syr|syr-sy|tl|tg|tg-cyrl|tg-cyrl-tj|ta|tt|te|th|bo|ti|ts|tn|tn-bw|"
    "tr|tk|uk|und|hsb|ur|ug|uz|ca-es|ve|vi|cy|fy|wo|xh|ii|yi|yo|zu"
)

# ---------------------------------------------------------------------------
# Metadata identification patterns (§7.3, §7.5)
#
# Each key maps to an ordered tuple of regex *strings*.  The config loader
# compiles them into ``re.Pattern`` objects.  Stored as strings here so that
# the defaults module has no compiled-pattern state of its own.
# ---------------------------------------------------------------------------

DEFAULT_METADATA_IDENTIFY_STRINGS: dict[str, tuple[str, ...]] = {
    "description": (
        r"\.description$",
    ),
    "desktop_ini": (
        r"\.desktop\.ini$",
        r"desktop\.ini$",
    ),
    "generic_metadata": (
        r"\.(exif|meta|metadata)$",
        r"\.comments$",
        r"^.(git(attributes|ignore))$",
        r"\.(cfg|conf|config)$",
        r"\.yaml$",
    ),
    "hash": (
        r"\.(md5|sha\d+|blake2[bs]|crc\d+|xxhash|checksum|hash)$",
    ),
    "json_metadata": (
        r"_directorymeta2?\.json$",
        r"_(subs|subtitles)\.json$",
        # BCP 47 language-code subtitles in JSON format
        r"\.(" + _BCP47_ALTERNATION + r")(-orig)?\.json$",
        r"_[a-z0-9]{3,19}\.json$",
        r"\.exifjson$",
        r"\.(AI|exif|info|meta)\.json$",
    ),
    "link": (
        r"\.(url|lnk|link|source)$",
    ),
    "screenshot": (
        r"(-|_)?(screen|screen(s|shot|shots)|thumb|thumb(nail|nails))"
        r"((-|_)?([0-9]{1,9}))?\.(jpg|jpeg|png|webp)$",
    ),
    "subtitles": (
        # Pattern 1: Language-tagged subtitle files (most specific)
        r"\.(" + _BCP47_ALTERNATION + r")(-orig)?\.(srt|sub|sbv|vtt|lrc|txt)$",
        # Pattern 2: Bare subtitle extensions (most generic)
        r"\.(srt|sub|sbv|vtt|lrc)$",
    ),
    "thumbnail": (
        r"\.(cover|thumb|thumb(s|db|index|nail))$",
        r"^(thumb|thumb(s|db|index|nail))\.db$",
    ),
    "torrent": (
        r"\.(torrent|magnet)$",
    ),
}

# Pre-compiled variant for direct access (used by the loader's ``build_config``).
DEFAULT_METADATA_IDENTIFY: dict[str, tuple[re.Pattern[str], ...]] = {
    type_name: tuple(re.compile(p, re.IGNORECASE) for p in patterns)
    for type_name, patterns in DEFAULT_METADATA_IDENTIFY_STRINGS.items()
}

# ---------------------------------------------------------------------------
# Metadata exclude patterns (§7.3 — Indexer include/exclude)
# ---------------------------------------------------------------------------

DEFAULT_METADATA_EXCLUDE_PATTERN_STRINGS: tuple[str, ...] = (
    r"_(meta2?|directorymeta2?)\.json$",
    r"\.(cover|thumb|thumb(s|db|index|nail))$",
    r"^(thumb|thumb(s|db|index|nail))\.db$",
)

DEFAULT_METADATA_EXCLUDE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in DEFAULT_METADATA_EXCLUDE_PATTERN_STRINGS
)

# ---------------------------------------------------------------------------
# Metadata type attributes (§7.3)
# ---------------------------------------------------------------------------

DEFAULT_METADATA_ATTRIBUTES: dict[str, MetadataTypeAttributes] = {
    "description": MetadataTypeAttributes(
        about=(
            "Likely a youtube-dl or yt-dlp information file containing UTF-8 text "
            "(with possible problematic characters)."
        ),
        expect_json=True,
        expect_text=True,
        expect_binary=False,
        parent_can_be_file=True,
        parent_can_be_directory=False,
    ),
    "desktop_ini": MetadataTypeAttributes(
        about=(
            "A Windows desktop.ini file used to customize folder appearance in "
            "Windows Explorer."
        ),
        expect_json=False,
        expect_text=True,
        expect_binary=True,
        parent_can_be_file=False,
        parent_can_be_directory=True,
    ),
    "generic_metadata": MetadataTypeAttributes(
        about=(
            "Generic metadata file which may contain any type of metadata "
            "information related to files or directories."
        ),
        expect_json=True,
        expect_text=True,
        expect_binary=True,
        parent_can_be_file=True,
        parent_can_be_directory=True,
    ),
    "hash": MetadataTypeAttributes(
        about="A file containing a hash value (MD5, SHA1, SHA256, etc.) of another file.",
        expect_json=False,
        expect_text=True,
        expect_binary=False,
        parent_can_be_file=True,
        parent_can_be_directory=False,
    ),
    "json_metadata": MetadataTypeAttributes(
        about=(
            "A JSON file containing metadata information related to files or "
            "directories."
        ),
        expect_json=True,
        expect_text=False,
        expect_binary=False,
        parent_can_be_file=True,
        parent_can_be_directory=True,
    ),
    "link": MetadataTypeAttributes(
        about=(
            "A file containing an Internet URL or a link to another file or "
            "directory."
        ),
        expect_json=False,
        expect_text=True,
        expect_binary=True,
        parent_can_be_file=True,
        parent_can_be_directory=True,
    ),
    "screenshot": MetadataTypeAttributes(
        about=(
            "A screenshot image file which may contain a screen capture of a "
            "computer desktop or application."
        ),
        expect_json=False,
        expect_text=False,
        expect_binary=True,
        parent_can_be_file=True,
        parent_can_be_directory=False,
    ),
    "subtitles": MetadataTypeAttributes(
        about=(
            "A subtitle file which contains text-based subtitles for a video or "
            "audio file."
        ),
        expect_json=True,
        expect_text=True,
        expect_binary=True,
        parent_can_be_file=True,
        parent_can_be_directory=False,
    ),
    "thumbnail": MetadataTypeAttributes(
        about=(
            "A thumbnail image file containing one or more reduced-size icon "
            "images related to another file or directory."
        ),
        expect_json=False,
        expect_text=False,
        expect_binary=True,
        parent_can_be_file=True,
        parent_can_be_directory=True,
    ),
    "torrent": MetadataTypeAttributes(
        about=(
            "A torrent or magnet link file containing connection and/or "
            "identification information for peer-to-peer retrieval."
        ),
        expect_json=False,
        expect_text=False,
        expect_binary=True,
        parent_can_be_file=True,
        parent_can_be_directory=True,
    ),
}

# ---------------------------------------------------------------------------
# Extension groups (§7.3)
#
# Carried forward verbatim from the original
# $MetadataFileParser.ExtensionGroups.  Duplicates are removed.
# ---------------------------------------------------------------------------

DEFAULT_EXTENSION_GROUPS: dict[str, tuple[str, ...]] = {
    "archive": (
        "7z", "ace", "alz", "arc", "arj", "bz", "bz2", "cab", "cbr", "cbz",
        "chm", "cpio", "deb", "dmg", "egg", "gz", "hdd", "img", "iso", "jar",
        "lha", "lz", "lz4", "lzh", "lzma", "lzo", "qcow2", "rar", "rpm",
        "s7z", "shar", "sit", "sitx", "sqx", "tar", "tbz", "tbz2", "tgz",
        "tlz", "txz", "vdi", "vhd", "vhdx", "vmdk", "war", "wim", "xar",
        "xz", "z", "zip", "zipx", "zoo", "zpaq", "zst", "zz",
    ),
    "audio": (
        "3ga", "8svx", "aa", "aac", "aax", "ac3", "act", "aiff", "alac",
        "amr", "ape", "au", "awb", "dct", "dss", "dvf", "flac", "gsm",
        "iklax", "ivs", "m4a", "m4b", "m4p", "m4r", "mid", "midi", "mka",
        "mlp", "mmf", "mp2", "mp3", "mpc", "msv", "ogg", "oga", "opus",
        "ra", "rm", "raw", "sln", "tta", "voc", "vox", "wav", "wma", "wv",
        "webm", "wvp", "wvpk",
    ),
    "font": (
        "eot", "otf", "svg", "svgz", "ttc", "ttf", "woff", "woff2",
    ),
    "image": (
        "3fr", "ari", "arw", "bay", "bmp", "cr2", "crw", "dcr", "dng",
        "erf", "fff", "gif", "gpr", "icns", "ico", "iiq", "jng", "jp2",
        "jpeg", "jpg", "k25", "kdc", "mef", "mos", "mrw", "nef", "nrw",
        "orf", "pbm", "pef", "pgm", "png", "ppm", "psd", "ptx", "raf",
        "raw", "rw2", "rwl", "sr2", "srf", "svg", "tga", "tif", "tiff",
        "webp", "x3f",
    ),
    "link": (
        "link", "lnk", "shortcut", "source", "symlink", "url",
    ),
    "subtitles": (
        "srt", "sub", "sbv", "vtt", "lrc",
    ),
    "video": (
        "3g2", "3gp", "3gp2", "3gpp", "amv", "asf", "avi", "divx", "drc",
        "dv", "f4v", "flv", "gvi", "gxf", "ismv", "m1v", "m2v", "m2t",
        "m2ts", "m4v", "mkv", "mov", "mp2", "mp2v", "mp4", "mp4v", "mpe",
        "mpeg", "mpeg1", "mpeg2", "mpeg4", "mpg", "mpv2", "mts", "mtv",
        "mxf", "nsv", "nuv", "ogm", "ogv", "ogx", "ps", "rec", "rm",
        "rmvb", "tod", "ts", "tts", "vob", "vro", "webm", "wm", "wmv",
        "wtv", "xesc",
    ),
}
