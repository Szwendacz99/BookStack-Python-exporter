# BookStack-Python-exporter
Customizable script for exporting notes from BookStack through API

#### Features:
- export keeping the tree structure by making folders from Shelves, Books and Chapters
- export multiple formats at once
- export at multiple levels at once (export Books or/and Chapters or/and Pages as files)
- choose if local files should be updated only if their edit timestamp is older than remote document last edit, or timestamps should be ignored and files will always be overwritten with the newest version
- customizable path for placing exported notes
- authorization token is loaded from txt file

Requirements:
- Python at least in version 3.6

Full example on how to use the script:
1. Clone the repo 
2. next to the script place token.txt file containing token id and token secret in format: TOKEN_ID:TOKEN_SECRET
3. in the same directory run the command, specifying your app domain with https prefix (every parameter is optional as it have default value, this is a full possible example):
```bash
python exporter.py \
    -H https://wiki.example.com \
    -f pdf md plaintext html \
    -l pages chapters books \
    --force-update-files \
    -t ./token.txt \
    -V debug \
    -p ./ 
```

Customization:
```text
options:
  -p PATH, --path PATH  Path where exported files will be placed.
  -t TOKEN_FILE, --token-file TOKEN_FILE
                        File containing authorization token in format TOKEN_ID:TOKEN_SECRET
  -H HOST, --host HOST  Your domain with protocol prefix, example: https://example.com
  -f {markdown,plaintext,pdf,html} [{markdown,plaintext,pdf,html} ...], 
                       --formats {markdown,plaintext,pdf,html} [{markdown,plaintext,pdf,html} ...]
                        Space separated list of formats to use for export.
  -l {pages,chapters,books} [{pages,chapters,books} ...], --level {pages,chapters,books} [{pages,chapters,books} ...]
                        Space separated list of levels at which should be export performed.
  --force-update-files  Set this option to skip checking local files timestamps against remote last edit
                        timestamps.This will cause overwriting local files, even if they seem to be already in
                        newest version.
  -V {debug,info,warning,error}, --log-level {debug,info,warning,error}
                        Set verbosity level.
```

### TODO:
- [x] ~~choosing verbosity level through command line parameter~~ Done
- [x] ~~choosing on what level should the notes be exported (Books, Chapters, Pages)~~ Done
- [x] ~~choosing if update note file only if the last edit timestamp from API is later that the local file timestamp~~ Done
- [ ] suggestions?
