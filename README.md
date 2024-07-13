# BookStack-Python-exporter
Customizable script for exporting notes from BookStack through API

#### Features:
- export keeping the tree structure by making folders from Shelves, Books, Chapters and attachments (including attachments from external links)
- export multiple formats at once
- export at multiple levels at once (export Books or/and Chapters or/and Pages as files)
- export images to specified dir in root export dir, preserving their paths
- (experimental) update markdown files before saving them to point to the downloaded image files instead of remote urls. Possible errors (low probability): replacing wrong parts/urls inside of the file, broken markdown encoding
- choose if local files should be updated only if their edit timestamp is older than remote document last edit, or timestamps should be ignored and files will always be overwritten with the newest version
- customizable path for placing exported notes
- configure replacing any characters in filenames with "_" for any filesystem compatibility
- authorization token is loaded from txt file
- Set custom HTTP User-Agent header to bypass filtering based on that header (like in CloudFlare tunnels)
- Set arbitrary custom headers through parameter

Requirements:
- Python at least in version 3.6

Full example on how to use the script:
1. Clone the repo 
2. next to the script place token.txt file containing token id and token secret in format: TOKEN_ID:TOKEN_SECRET
3. in the same directory run the command, specifying your app domain with https prefix (every parameter is optional as it have default value, this is an example):
```bash
python exporter.py \
    -H https://wiki.example.com \
    -f pdf markdown plaintext html \
    -l pages chapters books \
    --rate-limit 180 \
    -c "/" "#" \
    --force-update-files \
    --markdown-images \
    -t ./token.txt \
    -V debug \
    -p ./ \
    --user-agent "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/112.0"
    --additional-headers "Header1: value1" "Header2: value2"  
```

Customization:
```text
usage: exporter.py [-h] [-p PATH] [-t TOKEN_FILE] [-H HOST]
                   [-f {markdown,plaintext,pdf,html} [{markdown,plaintext,pdf,html} ...]]
                   [--rate-limit RATE_LIMIT] [-c FORBIDDEN_CHARS [FORBIDDEN_CHARS ...]]
                   [-u USER_AGENT]
                   [--additional-headers ADDITIONAL_HEADERS [ADDITIONAL_HEADERS ...]]
                   [-l {pages,chapters,books} [{pages,chapters,books} ...]]
                   [--force-update-files] [--images] [--markdown-images]
                   [--images-dir IMAGES_DIR] [--dont-export-attachments]
                   [--dont-export-external-attachments] [-V {debug,info,warning,error}]

BookStack exporter

options:
  -h, --help            show this help message and exit
  -p PATH, --path PATH  Path where exported files will be placed.
  -t TOKEN_FILE, --token-file TOKEN_FILE
                        File containing authorization token in format TOKEN_ID:TOKEN_SECRET
  -H HOST, --host HOST  Your domain with protocol prefix, example: https://example.com
  -f {markdown,plaintext,pdf,html} [{markdown,plaintext,pdf,html} ...], --formats {markdown,plaintext,pdf,html} [{markdown,plaintext,pdf,html} ...]
                        Space separated list of formats to use for export.
  --rate-limit RATE_LIMIT
                        How many api requests can be made in a minute. Default is 180
                        (BookStack defaults)
  -c FORBIDDEN_CHARS [FORBIDDEN_CHARS ...], --forbidden-chars FORBIDDEN_CHARS [FORBIDDEN_CHARS ...]
                        Space separated list of symbols to be replaced with "_" in filenames.
  -u USER_AGENT, --user-agent USER_AGENT
                        User agent header content. In situations where requests are blocked
                        because of bad client/unrecognized web browser/etc (like with
                        CloudFlare tunnels), change to some typical web browser user agent
                        header.
  --additional-headers ADDITIONAL_HEADERS [ADDITIONAL_HEADERS ...]
                        List of arbitrary additional HTTP headers to be sent with every HTTP
                        request. They can override default ones, including Authorization
                        header. IMPORTANT: these headers are also sent when downloading
                        external attachments! Don't put here any private data.Example: -u
                        "Header1: value1" "Header2: value2"
  -l {pages,chapters,books} [{pages,chapters,books} ...], --level {pages,chapters,books} [{pages,chapters,books} ...]
                        Space separated list of levels at which should be export performed.
  --force-update-files  Set this option to skip checking local files timestamps against remote
                        last edit timestamps. This will cause overwriting local files, even if
                        they seem to be already in newest version.
  --images              Download images and place them in dedicated directory in export path
                        root, preserving their internal paths
  --markdown-images     The same as --images, but will also update image links in exported
                        markdown files (if they are bein exported). Warning: this is
                        experimental, as API does not provide a way to know what images are
                        actually on the page. Therefore for markdown data all ']({URL}'
                        occurences will be replaced with local, relative path to images, and
                        additionally any '/scaled-\d+-/' regex match will be replaced with '/'
                        so that scaled images are also displayed
  --images-dir IMAGES_DIR
                        When exporting images, they will be organized in directory located at
                        the same path as exported document. This parameter defines name of
                        this directory.
  --dont-export-attachments
                        Set this to prevent exporting any attachments.
  --dont-export-external-attachments
                        Set this to prevent exporting external attachments (from links).
  -V {debug,info,warning,error}, --log-level {debug,info,warning,error}
                        Set verbosity level.
```

### TODO:
- [x] ~~choosing verbosity level through command line parameter~~ Done
- [x] ~~choosing on what level should the notes be exported (Books, Chapters, Pages)~~ Done
- [x] ~~choosing if update note file only if the last edit timestamp from API is later that the local file timestamp~~ Done
- [x] ~~exporting attachments~~
- [x] ~~api rate limiting~~
- [x] ~~images exporting~~
- [ ] suggestions?
