import argparse
import json
import logging
import os
from datetime import datetime
from logging import info, error, debug
from pathlib import Path
from urllib.request import urlopen, Request

# (formatName, fileExtension)
FORMATS: dict['str', 'str'] = {
    'markdown': 'md',
    'plaintext': 'txt',
    'pdf': 'pdf',
    'html': 'html'
}

LEVELS = [
    'pages',
    'chapters',
    'books'
]

LOG_LEVEL: dict = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR
}

parser = argparse.ArgumentParser(description='BookStack exporter')
parser.add_argument('-p', '--path', type=str, default='.',
                    help='Path where exported files will be placed.')
parser.add_argument('-t', '--token-file', type=str, default=f'.{os.path.sep}token.txt',
                    help='File containing authorization token in format TOKEN_ID:TOKEN_SECRET')
parser.add_argument('-H', '--host', type=str, default='https://localhost',
                    help='Your domain with protocol prefix, example: https://example.com')
parser.add_argument('-f', '--formats', type=str, default='markdown',
                    help=f'Coma separated list of formats to use for export.'
                         f' Available ones: {",".join([f for f in FORMATS.keys()])}')
parser.add_argument('-l', '--level', type=str, default='pages',
                    help=f'Coma separated list of levels at which should be export performed. '
                         f'Available levels: {LEVELS}')
parser.add_argument('-V', '--log-level', type=str, default='info',
                    help=f'Set verbosity level. '
                         f'Available levels: {LOG_LEVEL.keys()}')

args = parser.parse_args()

if args.log_level not in LOG_LEVEL.keys():
    error(f"Bad log level {args.log_level}, available levels: {LOG_LEVEL.keys()}")
    exit(1)

logging.basicConfig(format='%(levelname)s :: %(message)s', level=LOG_LEVEL.get(args.log_level))

formats = args.formats.split(',')
for frmt in formats:
    if frmt not in FORMATS.keys():
        error("Unknown format name (NOT file extension), "
              "check api docs for current version of your BookStack")
        exit(1)

API_PREFIX: str = f"{args.host.removesuffix(os.path.sep)}/api"
FS_PATH: str = args.path.removesuffix(os.path.sep)
LEVEL_CHOICE: list[str] = args.level.split(',')
for lvl in LEVEL_CHOICE:
    if lvl not in LEVELS:
        error(f"Level {lvl} is not supported, can be only one of {LEVELS}")
        exit(1)

with open(args.token_file, 'r') as f:
    TOKEN: str = f.readline().removesuffix('\n')

HEADERS = {'Content-Type': 'application/json; charset=utf-8',
           'Authorization': f"Token {TOKEN}"}


class Node:
    def __init__(self, name: str, parent: ['Node', None], node_id: int):
        self.__name: str = name
        self.__parent: ['Node', None] = parent
        self.__node_id = node_id

    def get_name(self) -> str:
        return self.__name

    def get_parent(self) -> ['Node', None]:
        return self.__parent

    def set_parent(self, parent: 'Node'):
        self.__parent = parent

    def get_path(self) -> str:
        if self.__parent is None:
            return "."
        return self.__parent.get_path() + os.path.sep + self.__parent.get_name()

    def get_id(self) -> int:
        return self.__node_id


shelves: dict[int, Node] = {}
books: dict[int, Node] = {}
chapters: dict[int, Node] = {}
pages: dict[int, Node] = {}
pages_not_in_chapter: dict[int, Node] = {}


def make_dir(path: str):
    path_obj = Path(path)
    if path_obj.exists():
        return
    info(f"Creating dir {path}")
    path_obj.mkdir(exist_ok=True, parents=True)


def api_get_bytes(path: str) -> bytes:
    request: Request = Request(f'{API_PREFIX}/{path}', headers=HEADERS)

    with urlopen(request) as response:
        response = response
        if response.status == 403:
            error("403 Forbidden, check your token!")
            exit(response.status)

        return response.read()


def api_get_dict(path: str) -> dict:
    return json.loads(api_get_bytes(path).decode())


def check_if_update_needed(file: str, remote_last_edit: datetime) -> bool:
    if not os.path.exists(file):
        return True
    local_last_edit: datetime = datetime.fromtimestamp(os.path.getmtime(file))
    debug(f"Local file creation timestamp: {local_last_edit.date()} {local_last_edit.time()}, "
          f"remote edit timestamp:  {remote_last_edit.date()} {remote_last_edit.time()}")
    return local_last_edit.timestamp() < remote_last_edit.timestamp()


def export(files: list[Node], level: str):
    for file in files:
        make_dir(f"{FS_PATH}{os.path.sep}{file.get_path()}")

        file_info: dict = api_get_dict(f'{level}/{file.get_id()}')
        last_edit_time: datetime = datetime.strptime(file_info['updated_at'], '%Y-%m-%dT%H:%M:%S.%fZ')

        for frmt in formats:
            path: str = f"{FS_PATH}{os.path.sep}{file.get_path()}{os.path.sep}{file.get_name()}.{FORMATS[frmt]}"
            debug(f"Checking for update for file {path}")
            if not check_if_update_needed(path, last_edit_time):
                debug("Already updated")
                continue

            data: bytes = api_get_bytes(f'{level}/{file.get_id()}/export/{frmt}')
            with open(path, 'wb') as f:
                info(f"Saving {path}")
                f.write(data)


info("Getting info about Shelves and their Books")

for shelf_data in api_get_dict('shelves').get('data'):
    shelf = Node(shelf_data.get('name'), None, shelf_data.get('id'))
    shelves[shelf.get_id()] = shelf

    shelf_details = api_get_dict(f'shelves/{shelf.get_id()}')

    if shelf_details.get('books') is None:
        continue
    for book_data in shelf_details.get('books'):
        book = Node(book_data.get('name'), shelf, book_data.get('id'))
        books[book.get_id()] = book

info("Getting info about Books not belonging to any shelf")

for book_data in api_get_dict('books').get('data'):
    if book_data.get('id') in books.keys():
        continue
    book = Node(book_data.get('name'), None, book_data.get('id'))
    info(f"Book \"{book.get_name()} has no shelf assigned.\"")
    books[book.get_id()] = book

info("Getting info about Chapters")

for chapter_data in api_get_dict('chapters').get('data'):
    chapter = Node(chapter_data.get('name'), books.get(chapter_data.get('book_id')), chapter_data.get('id'))
    chapters[chapter.get_id()] = chapter

info("Getting info about Pages")

for page_data in api_get_dict('pages').get('data'):
    parent_id = page_data.get('chapter_id')
    if parent_id not in chapters.keys():
        parent_id = page_data.get('book_id')
        info(f"Page \"{page_data.get('name')}\" is not in any chapter, "
             f"using Book \"{books.get(parent_id).get_name()}\" as a parent.")
        page = Node(page_data.get('name'), books.get(parent_id), page_data.get('id'))
        pages[page.get_id()] = page
        pages_not_in_chapter[page.get_id()] = page
        continue

    page = Node(page_data.get('name'), chapters.get(parent_id), page_data.get('id'))
    pages[page.get_id()] = page

files: list[Node] = []
export_pages_not_in_chapter: bool = False

for lvl in LEVEL_CHOICE:
    if lvl == 'pages':
        files = pages.values()
    elif lvl == 'chapters':
        files = chapters.values()
        export_pages_not_in_chapter = True
    elif lvl == 'books':
        files = books.values()
    export(files, lvl)

if export_pages_not_in_chapter:
    info("Exporting pages that are not in chapter...")
    export(pages_not_in_chapter.values(), 'pages')
