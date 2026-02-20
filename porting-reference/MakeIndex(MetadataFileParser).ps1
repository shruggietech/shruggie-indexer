<#
.SYNOPSIS
    Isolated MetadataFileParser object
.DESCRIPTION
    This script defines a MetadataFileParser object which contains properties and methods related to identifying and categorizing metadata files based on their names, extensions, and expected content types.

    The object includes various categories of metadata files:

    - Description
    - DesktopIni
    - GenericMetadata
    - Hash
    - JsonMetadata
    - Link
    - Screenshot
    - Subtitles
    - Thumbnail
    - Torrent

    Each category has specific attributes that describe the expected content and parent types.

    The Identify property contains regular expressions for detecting each category of metadata file based on their names and extensions.

    The Exiftool property specifies which file types to include or exclude when using Exiftool for metadata extraction.

    The ExtensionGroups property categorizes common file extensions into groups:

    - Archive
    - Audio
    - Font
    - Image
    - Link
    - Subtitles
    - Video

    Finally, the Indexer property is used to create a combined list of regular expressions for identifying metadata files during indexing.
#>
[CmdletBinding(SupportsShouldProcess=$false,ConfirmImpact='None',DefaultParameterSetName='Default')]
Param(
    [Parameter(Mandatory=$true,ParameterSetName='HelpText')]
    [Alias("h")]
    [Switch]$Help
)
#______________________________________________________________________________
## Declare Variables and Arrays and set Alias assignments

    $HereNow = ($PWD | Select-Object -Expand Path) -join '`n'
    $ThisScriptPath = $MyInvocation.MyCommand.Path
    $ThisScriptName = $MyInvocation.MyCommand.Name
    $ThisScript = $ThisScriptPath | Split-Path -Leaf
    $thisFunction = "{0}" -f $MyInvocation.MyCommand
    # Declare the multi-use MetadataFileParser object
    #
    # References:
    #
    # - https://svn.apache.org/repos/asf/httpd/httpd/trunk/docs/conf/mime.types
    # - https://cdn.jsdelivr.net/gh/jshttp/mime-db@master/db.json
    # - https://github.com/sindresorhus/archive-extensions/blob/main/archive-extensions.json
    # - https://github.com/sindresorhus/binary-extensions/blob/main/binary-extensions.json
    # - https://github.com/sindresorhus/compressed-extensions/blob/main/compressed-extensions.json
    # - https://github.com/sindresorhus/markdown-extensions/blob/main/markdown-extensions.json
    # - https://github.com/sindresorhus/text-extensions/blob/main/text-extensions.json
    # - https://github.com/sindresorhus/video-extensions/blob/main/video-extensions.json
    # - https://github.com/stretchr/filetypes.js/blob/master/src/filetypes.js
    # - https://github.com/dannyroemhild/ransomware-fileext-list/blob/master/fileextlist.txt
    #
    $global:MetadataFileParser = [ordered]@{
        Attributes = [ordered]@{
            Description = [ordered]@{
                About = 'Likely a youtube-dl or yt-dlp information file which contains UTF8 text (with possible problematic characters).'
                ExpectJson = $true
                ExpectText = $true
                ExpectBinary = $false
                ParentCanBeFile = $true
                ParentCanBeDirectory = $false
            }
            DesktopIni = [ordered]@{
                About = 'A Windows desktop.ini file used in customizing the appearance of files and folders in Windows Explorer.'
                ExpectJson = $false
                ExpectText = $true
                ExpectBinary = $true
                ParentCanBeFile = $false
                ParentCanBeDirectory = $true
            }
            GenericMetadata = [ordered]@{
                About = 'Generic metadata file which may contain any type of metadata information related to files or directories.'
                ExpectJson = $true
                ExpectText = $true
                ExpectBinary = $true
                ParentCanBeFile = $true
                ParentCanBeDirectory = $true
            }
            Hash = [ordered]@{
                About = 'A file containing a hash value (MD5, SHA1, SHA256, etc.) of another file.'
                ExpectJson = $false
                ExpectText = $true
                ExpectBinary = $false
                ParentCanBeFile = $true
                ParentCanBeDirectory = $false
            }
            JsonMetadata = [ordered]@{
                About = 'A JSON file containing metadata information related to files or directories.'
                ExpectJson = $true
                ExpectText = $false
                ExpectBinary = $false
                ParentCanBeFile = $true
                ParentCanBeDirectory = $true
            }
            Link = [ordered]@{
                About = 'A file containing an Internet URL or a link to another file or directory.'
                ExpectJson = $false
                ExpectText = $true
                ExpectBinary = $true
                ParentCanBeFile = $true
                ParentCanBeDirectory = $true
            }
            Screenshot = [ordered]@{
                About = 'A screenshot image file which may contain a screen capture of a computer desktop or application.'
                ExpectJson = $false
                ExpectText = $false
                ExpectBinary = $true
                ParentCanBeFile = $true
                ParentCanBeDirectory = $false
            }
            Subtitles = [ordered]@{
                About = 'A subtitle file which contains text-based subtitles for a video or audio file.'
                ExpectJson = $true
                ExpectText = $true
                ExpectBinary = $true
                ParentCanBeFile = $true
                ParentCanBeDirectory = $false
            }
            Thumbnail = [ordered]@{
                About = 'A thumbnail image file which contains one or more reduced-size icon images related to another file or directory.'
                ExpectJson = $false
                ExpectText = $false
                ExpectBinary = $true
                ParentCanBeFile = $true
                ParentCanBeDirectory = $true
            }
            Torrent = [ordered]@{
                About = 'A torrent or magnet link file contains connection and/or identification information related to retrieving a file or directory from a peer-to-peer network.'
                ExpectJson = $false
                ExpectText = $false
                ExpectBinary = $true
                ParentCanBeFile = $true
                ParentCanBeDirectory = $true
            }
        }
        Identify = [ordered]@{
            # Detection parsers for the metadata categories covered by this parser
            ## Array elements are generally ordered from most specific to most generic (when applicable)
            Description = @(
                '\.description$'
            )
            DesktopIni = @(
                '\.desktop\.ini$',
                'desktop\.ini$'
            )
            GenericMetadata = @(
                '\.(exif|meta|metadata)$',
                '\.comments$',
                '^.(git(attributes|ignore))$',
                '\.(cfg|conf|config)$',
                '\.yaml$'
            )
            Hash = @(
                '\.(md5|sha\d+|blake2[bs]|crc\d+|xxhash|checksum|hash)$'
            )
            JsonMetadata = @(
                '_directorymeta\.json$',
                # Json-formatted subtitle files
                '_(subs|subtitles)\.json$',
                # Json-formatted subtitles with language codes
                '\.(aa|af|sq|gsw-fr|ase|am|ar|arq|abv|arz|acm|ajp|afb-kw|apc|ayl|ary|acx|afb-qa|ar-sa|ar-sy|aeb|ar-ae|ar-ye|arp|hy|as|az|az-cyrl|az-latn|ba|be|bn|bn-in|bs|bs-cyrl|bzs|br|br-fr|bg|my|ca|tzm|tzm-arab-ma|tzm-dz|tzm-tfng|tzm-tfng-ma|ckb|ckb-iq|chr|zh|yue|yue-hk|cmn|cmn-hans|cmn-hans-cn|cmn-hans-hk|cmn-hans-mo|cmn-hans-my|cmn-hans-sg|cmn-hans-tw|cmn-tw|cmn-hant|cmn-hant-cn|cmn-hant-hk|cmn-hant-mo|cmn-hant-my|cmn-hant-sg|cmn-hant-tw|nan|zh-hans|zh-hans-cn|zh-hans-hk|zh-hans-mo|zh-hans-my|zh-hans-sg|zh-hans-tw|zh-hant|zh-hant-cn|zh-hant-hk|zh-hant-mo|zh-hant-my|zh-hant-sg|zh-hant-tw|com|co|co-fr|hr|hr-ba|quz|cs|da|prs|dv|nl|dz|bin|en|en-au|en-bz|en-ca|en-029|en-hk|en-in|en-id|en-ie|en-jm|en-my|en-nz|en-ph|en-sg|en-za|en-se|en-tt|en-ae|en-gb|en-us|en-zw|et|eu|fo|fil|fi|nl-be|fr|fr-be|fr-cm|fr-ca|fr-029|fr-ci|fr-ht|fr-lu|fr-ml|fr-mc|fr-ma|fr-re|fr-sn|fr-ch|fr-cd|ff|ff-latn|ff-latn-ng|ff-latn-sn|ff-ng|gl|ka|de|de-at|de-li|de-lu|gsw|de-ch|el|gn|gu|ha|ha-latn|ha-latn-ng|haw|he|hi|hu|ibb|is|ig|id|iu|iu-cans|ga|it|it-ch|ja|ja-jp|quc|kl|kn|kr|kr-ng|ks|ks-deva-in|kk|km|rw|kok|ko|ky|lad|lo|la|la-va|lv|ln|lt|dsb|lb|mk|ms-bn|ms-my|ms|ml|mt|mni|mni-beng-in|mi|arn|mr|fit|moh|mn|mn-cn|mn-mong|mn-mong-cn|nv|ne|ne-in|no|nb|nn|oc|or|om|pap|pap-029|ps|fa|pl|pt-br|pt|pa|pa-arab|qu|qu-bo|qu-ec|qu-pe|ro|ro-md|rm|ru|ru-md|aec|sah|smi|smn|smj|smj-no|se|se-fi|se-no|se-se|sms|sma|sma-no|sm|sa|gd|sr|sr-cyrl|sr-ba|sr-cyrl-me|sr-latn|sr-latn-ba|sr-me|sd|sd-arab|sd-in|si|sk|sl|so|st|nso|es-ar|es-bo|es|es-cl|es-co|es-cr|es-cu|es-do|es-ec|es-sv|es-gt|es-hn|es-419|es-mx|es-ni|es-pa|es-py|es-pe|es-pr|es-us|es-uy|es-ve|sw|sw-ke|sv|sv-fi|syr|syr-sy|tl|tg|tg-cyrl|tg-cyrl-tj|ta|tt|te|th|bo|ti|ts|tn|tn-bw|tr|tk|uk|und|hsb|ur|ug|uz|ca-es|ve|vi|cy|fy|wo|xh|ii|yi|yo|zu)(-orig)?\.json$',
                '_[a-z0-9]{3,19}\.json$',
                '\.exifjson$',
                '\.(AI|exif|info|meta)\.json$'
            )
            Link = @(
                '\.(url|lnk|link|source)$'
            )
            Screenshot = @(
                '(-|_)?(screen|screen(s|shot|shots)|thumb|thumb(nail|nails))((-|_)?([0-9]{1,9}))?\.(jpg|jpeg|png|webp)$'
            )
            Subtitles = @(
                # This order is important: The first regex is the most specific and the second regex is the most generic.
                '\.(aa|af|sq|gsw-fr|ase|am|ar|arq|abv|arz|acm|ajp|afb-kw|apc|ayl|ary|acx|afb-qa|ar-sa|ar-sy|aeb|ar-ae|ar-ye|arp|hy|as|az|az-cyrl|az-latn|ba|be|bn|bn-in|bs|bs-cyrl|bzs|br|br-fr|bg|my|ca|tzm|tzm-arab-ma|tzm-dz|tzm-tfng|tzm-tfng-ma|ckb|ckb-iq|chr|zh|yue|yue-hk|cmn|cmn-hans|cmn-hans-cn|cmn-hans-hk|cmn-hans-mo|cmn-hans-my|cmn-hans-sg|cmn-hans-tw|cmn-tw|cmn-hant|cmn-hant-cn|cmn-hant-hk|cmn-hant-mo|cmn-hant-my|cmn-hant-sg|cmn-hant-tw|nan|zh-hans|zh-hans-cn|zh-hans-hk|zh-hans-mo|zh-hans-my|zh-hans-sg|zh-hans-tw|zh-hant|zh-hant-cn|zh-hant-hk|zh-hant-mo|zh-hant-my|zh-hant-sg|zh-hant-tw|com|co|co-fr|hr|hr-ba|quz|cs|da|prs|dv|nl|dz|bin|en|en-au|en-bz|en-ca|en-029|en-hk|en-in|en-id|en-ie|en-jm|en-my|en-nz|en-ph|en-sg|en-za|en-se|en-tt|en-ae|en-gb|en-us|en-zw|et|eu|fo|fil|fi|nl-be|fr|fr-be|fr-cm|fr-ca|fr-029|fr-ci|fr-ht|fr-lu|fr-ml|fr-mc|fr-ma|fr-re|fr-sn|fr-ch|fr-cd|ff|ff-latn|ff-latn-ng|ff-latn-sn|ff-ng|gl|ka|de|de-at|de-li|de-lu|gsw|de-ch|el|gn|gu|ha|ha-latn|ha-latn-ng|haw|he|hi|hu|ibb|is|ig|id|iu|iu-cans|ga|it|it-ch|ja|ja-jp|quc|kl|kn|kr|kr-ng|ks|ks-deva-in|kk|km|rw|kok|ko|ky|lad|lo|la|la-va|lv|ln|lt|dsb|lb|mk|ms-bn|ms-my|ms|ml|mt|mni|mni-beng-in|mi|arn|mr|fit|moh|mn|mn-cn|mn-mong|mn-mong-cn|nv|ne|ne-in|no|nb|nn|oc|or|om|pap|pap-029|ps|fa|pl|pt-br|pt|pa|pa-arab|qu|qu-bo|qu-ec|qu-pe|ro|ro-md|rm|ru|ru-md|aec|sah|smi|smn|smj|smj-no|se|se-fi|se-no|se-se|sms|sma|sma-no|sm|sa|gd|sr|sr-cyrl|sr-ba|sr-cyrl-me|sr-latn|sr-latn-ba|sr-me|sd|sd-arab|sd-in|si|sk|sl|so|st|nso|es-ar|es-bo|es|es-cl|es-co|es-cr|es-cu|es-do|es-ec|es-sv|es-gt|es-hn|es-419|es-mx|es-ni|es-pa|es-py|es-pe|es-pr|es-us|es-uy|es-ve|sw|sw-ke|sv|sv-fi|syr|syr-sy|tl|tg|tg-cyrl|tg-cyrl-tj|ta|tt|te|th|bo|ti|ts|tn|tn-bw|tr|tk|uk|und|hsb|ur|ug|uz|ca-es|ve|vi|cy|fy|wo|xh|ii|yi|yo|zu)(-orig)?\.(srt|sub|sbv|vtt|lrc|txt)$',
                '\.(srt|sub|sbv|vtt|lrc)$'
            )
            Thumbnail = @(
                '\.(cover|thumb|thumb(s|db|index|nail))$',
                '^(thumb|thumb(s|db|index|nail))\.db$'
            )
            Torrent = @(
                '\.(torrent|magnet)$'
            )
        }
        Exiftool = [ordered]@{
            Exclude = @(
                'csv',
                'htm',
                'html',
                'json',
                'tsv',
                'xml'
            )
            Include = @(
                '*'
            )
        }
        ExtensionGroups = [ordered]@{
            Archive = @(
                '7z',
                'ace',
                'alz',
                'arc',
                'arj',
                'bz',
                'bz2',
                'cab',
                'cbr',
                'cbz',
                'chm',
                'cpio',
                'deb',
                'dmg',
                'egg',
                'gz',
                'hdd',
                'img',
                'iso',
                'jar',
                'lha',
                'lz',
                'lz4',
                'lzh',
                'lzma',
                'lzo',
                'qcow2',
                'rar',
                'rpm',
                's7z',
                'shar',
                'sit',
                'sitx',
                'sqx',
                'tar',
                'tbz',
                'tbz2',
                'tgz',
                'tlz',
                'txz',
                'vdi',
                'vhd',
                'vhdx',
                'vmdk',
                'war',
                'wim',
                'xar',
                'xz',
                'z',
                'zip',
                'zipx',
                'zoo',
                'zpaq',
                'zst',
                'zz'
            )
            Audio = @(
                '3ga',
                '8svx',
                'aa',
                'aac',
                'aax',
                'ac3',
                'act',
                'aiff',
                'alac',
                'amr',
                'ape',
                'au',
                'awb',
                'dct',
                'dss',
                'dvf',
                'flac',
                'gsm',
                'iklax',
                'ivs',
                'm4a',
                'm4b',
                'm4p',
                'm4r',
                'mid',
                'midi',
                'mka',
                'mlp',
                'mmf',
                'mp2',
                'mp3',
                'mpc',
                'msv',
                'ogg',
                'oga',
                'opus',
                'ra',
                'rm',
                'raw',
                'sln',
                'tta',
                'voc',
                'vox',
                'wav',
                'wma',
                'wv',
                'webm',
                'wv',
                'wvp',
                'wvpk'
            )
            Font = @(
                'eot',
                'otf',
                'svg',
                'svgz',
                'ttc',
                'ttf',
                'woff',
                'woff2'
            )
            Image = @(
                '3fr',
                'ari',
                'arw',
                'bay',
                'bmp',
                'cr2',
                'crw',
                'dcr',
                'dng',
                'erf',
                'fff',
                'gif',
                'gpr',
                'icns',
                'ico',
                'iiq',
                'jng',
                'jp2',
                'jpeg',
                'jpg',
                'k25',
                'kdc',
                'mef',
                'mos',
                'mrw',
                'nef',
                'nrw',
                'orf',
                'pbm',
                'pef',
                'pgm',
                'png',
                'ppm',
                'psd',
                'ptx',
                'raf',
                'raw',
                'rw2',
                'rwl',
                'sr2',
                'srf',
                'svg',
                'tga',
                'tif',
                'tiff',
                'webp',
                'x3f'
            )
            Link = @(
                'link',
                'lnk',
                'shortcut',
                'source',
                'symlink',
                'url'
            )
            Subtitles = @(
                'srt',
                'sub',
                'sbv',
                'vtt',
                'lrc'
            )
            Video = @(
                '3g2',
                '3gp',
                '3gp2',
                '3gpp',
                'amv',
                'asf',
                'avi',
                'divx',
                'drc',
                'dv',
                'f4v',
                'flv',
                'gvi',
                'gxf',
                'ismv',
                'm1v',
                'm2v',
                'm2t',
                'm2ts',
                'm4v',
                'mkv',
                'mov',
                'mp2',
                'mp2v',
                'mp4',
                'mp4v',
                'mpe',
                'mpeg',
                'mpeg1',
                'mpeg2',
                'mpeg4',
                'mpg',
                'mpv2',
                'mts',
                'mtv',
                'mxf',
                'nsv',
                'nuv',
                'ogm',
                'ogv',
                'ogx',
                'ps',
                'rec',
                'rm',
                'rmvb',
                'tod',
                'ts',
                'tts',
                'vob',
                'vro',
                'webm',
                'wm',
                'wmv',
                'wtv',
                'xesc'
            )
        }
        Indexer = [ordered]@{
            Exclude = @(
                '_(meta|directorymeta)\.json$',
                '\.(cover|thumb|thumb(s|db|index|nail))$',
                '^(thumb|thumb(s|db|index|nail))\.db$'
            )
        }
    }
    # Create the Indexer Include array by iterating through every array found in the Identify sub-object
    $MetadataFileParser.Indexer.Include = @()
    ForEach ($Key in $MetadataFileParser.Identify.Keys) {
        ForEach ($Parser in $MetadataFileParser.Identify.$Key) {
            $MetadataFileParser.Indexer.Include += $Parser
        }
    }
    # Add all-in-one string variants of the indexer include and exclude arrays
    $MetadataFileParser.Indexer.ExcludeString = ($MetadataFileParser.Indexer.Exclude -join '|')
    $MetadataFileParser.Indexer.IncludeString = ($MetadataFileParser.Indexer.Include -join '|')

#______________________________________________________________________________
## Execute Operations

    # Catch help text requests
    if (($Help) -or ($PSCmdlet.ParameterSetName -eq 'HelpText')) {
        Get-Help $ThisScriptPath -Detailed
        exit
    }

#______________________________________________________________________________
## End