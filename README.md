# BookStack-Python-exporter
Customizable script for exporting notes from BookStack through API

#### Features:
- export keeping the tree structure by making folders from Shelves, Books and Chapters
- export multiple formats at once
- customizable path for placing exported notes
- authorization token is loaded from txt file

Requirements:
- Python at least in version 3.6

Full example on how to use the script:
1. Clone the repo 
2. next to the script place token.txt file containing token id and token secret in format: TOKEN_ID:TOKEN_SECRET
3. in the same directory run the command, specifying your app domain with https prefix:
```bash
python exporter.py -H https://wiki.example.com -f pdf,md,plaintext,html -t ./token.txt -p ./
```

Customization:
```text
  -p PATH, --path PATH  Path where exported files will be placed.
                        Default: .
  -t TOKEN_FILE, --token-file TOKEN_FILE
                        File containing authorization token in format TOKEN_ID:TOKEN_SECRET
                        Default: ./token.txt
  -H HOST, --host HOST  Your domain with protocol prefix, example: https://example.com
                        Default: https://localhost
  -f FORMATS, --formats FORMATS
                        Coma separated list of formats to use for export. Available ones: md,plaintext,pdf,html
                        Default: md
```

### TODO:
- choosing verbosity level through command line parameter
- choosing on what level should the notes be exported (Books, Chapters, Pages)
- (optional) choosing if update note file only if the last edit timestamp from API is later that the local file timestamp
- suggestions?
