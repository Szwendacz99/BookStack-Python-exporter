import argparse
import json
import logging
import os
from datetime import datetime
from logging import info, error, debug
from pathlib import Path
from typing import Union
from urllib.request import urlopen, Request
import urllib.parse

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
parser.add_argument('-f', '--formats', type=str, default=['markdown'], nargs="+",
                    help=f'Space separated list of formats to use for export.', choices=FORMATS.keys())
parser.add_argument('-l', '--level', type=str, default=['pages'], nargs="+",
                    help=f'Space separated list of levels at which should be export performed. ', choices=LEVELS)
parser.add_argument('--force-update-files', action='store_true',
                    help="Set this option to skip checking local files timestamps against remote last edit timestamps."
                         "This will cause overwriting local files, even if they seem to be already in newest version.")
parser.set_defaults(force_update_files=False)
parser.add_argument('-V', '--log-level', type=str, default='info',
                    help=f'Set verbosity level. ', choices=LOG_LEVEL.keys())

args = parser.parse_args()

logging.basicConfig(format='%(levelname)s :: %(message)s', level=LOG_LEVEL.get(args.log_level))

formats: list[str] = args.formats

for frmt in formats:
    if frmt not in FORMATS.keys():
        error("Unknown format name (NOT file extension), "
              "check api docs for current version of your BookStack")
        exit(1)

API_PREFIX: str = f"{args.host.removesuffix(os.path.sep)}/api"
FS_PATH: str = args.path.removesuffix(os.path.sep)
LEVEL_CHOICE: list[str] = args.level
for lvl in LEVEL_CHOICE:
    if lvl not in LEVELS:
        error(f"Level {lvl} is not supported, can be only one of {LEVELS}")
        exit(1)

with open(args.token_file, 'r') as f:
    TOKEN: str = f.readline().removesuffix('\n')

HEADERS = {'Content-Type': 'application/json; charset=utf-8',
           'Authorization': f"Token {TOKEN}"}
SKIP_TIMESTAMPS: bool = args.force_update_files


class Node:
    def __init__(self, name: str,
                 parent: Union['Node', None],
                 node_id: int,
                 last_edit_timestamp: datetime):
        self.__name: str = name
        self.__children: list['Node'] = []

        self.__parent: Union['Node', None] = parent
        if parent is not None:
            parent.add_child(self)

        self.__last_edit_timestamp: datetime = last_edit_timestamp
        self.__node_id = node_id

    def get_name(self) -> str:
        return self.__name

    def get_parent(self) -> Union['Node', None]:
        return self.__parent

    def changed_since(self, timestamp: datetime) -> int:
        """
        Check if remote version have changed after given timestamp, including its children
        :param timestamp:
        :return: amount of changed documents at level of this document Node
        """
        result: int = 0
        if self.__last_edit_timestamp > timestamp:
            result += 1
        for child in self.__children:
            result += child.changed_since(timestamp)

        return result

    def get_last_edit_timestamp(self) -> datetime:
        return self.__last_edit_timestamp

    def set_parent(self, parent: 'Node'):
        self.__parent = parent
        parent.add_child(self)

    def add_child(self, child: 'Node'):
        self.__children.append(child)

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


def api_timestamp_string_to_datetime(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')


def make_dir(path: str):
    path_obj = Path(path)
    if path_obj.exists():
        return
    info(f"Creating dir {path}")
    path_obj.mkdir(exist_ok=True, parents=True)


def api_get_bytes(path: str, **kwargs) -> bytes:
    request_path: str = f'{API_PREFIX}/{path}'

    if len(kwargs) > 0:
        params: str = urllib.parse.urlencode(kwargs)
        request_path += f"?{params}"

    debug(f"Making http request: {request_path}")

    request: Request = Request(request_path, headers=HEADERS)

    with urlopen(request) as response:
        if response.status == 403:
            error("403 Forbidden, check your token!")
            exit(response.status)

        return response.read()


def api_get_dict(path: str) -> dict:
    data = api_get_bytes(path).decode()
    return json.loads(data)


def api_get_listing(path: str) -> list:
    """
    function for retrieving whole lists through api, it will
    request for another 50 until have collected "total" amount
    :param path:
    :return:
    """
    count: int = 50
    total: int = count

    result: list = []

    while total > len(result):
        data: dict = json.loads(api_get_bytes(path, count=count, offset=len(result)))
        total = data.get('total')
        result += data.get('data')

        debug(f"API listing got {total} items out of maximum {count}")

    return result


def check_if_update_needed(file_path: str, document: Node) -> bool:
    if SKIP_TIMESTAMPS:
        return True
    debug(f"Checking for update for file {file_path}")

    if not os.path.exists(file_path):
        debug(f"Document {file_path} is missing on disk, update needed.")
        return True
    local_last_edit: datetime = datetime.utcfromtimestamp(os.path.getmtime(file_path))
    remote_last_edit: datetime = document.get_last_edit_timestamp()

    debug(f"Local file creation timestamp: {local_last_edit.date()} {local_last_edit.time()}, "
          f"remote edit timestamp:  {remote_last_edit.date()} {remote_last_edit.time()}")
    changes: int = document.changed_since(local_last_edit)

    if changes > 0:
        info(f"Document \"{file_path}\" consists of {changes} outdated documents, update needed.")
        return True

    debug(f"Document \"{file_path}\" consists of {changes} outdated documents, skipping updating.")
    return False


def export(documents: list[Node], level: str):
    for document in documents:
        make_dir(f"{FS_PATH}{os.path.sep}{document.get_path()}")

        for frmt in formats:
            path: str = f"{FS_PATH}{os.path.sep}{document.get_path()}{os.path.sep}{document.get_name()}.{FORMATS[frmt]}"

            if not check_if_update_needed(path, document):
                continue

            data: bytes = api_get_bytes(f'{level}/{document.get_id()}/export/{frmt}')
            with open(path, 'wb') as f:
                info(f"Saving {path}")
                f.write(data)


info("Getting info about Shelves and their Books")

for shelf_data in api_get_listing('shelves'):

    last_edit_timestamp: datetime = api_timestamp_string_to_datetime(shelf_data['updated_at'])
    shelf = Node(shelf_data.get('name'), None, shelf_data.get('id'), last_edit_timestamp)

    debug(f"Shelf: \"{shelf.get_name()}\", ID: {shelf.get_id()}")
    shelves[shelf.get_id()] = shelf

    shelf_details = api_get_dict(f'shelves/{shelf.get_id()}')

    if shelf_details.get('books') is None:
        continue
    for book_data in shelf_details.get('books'):

        last_edit_timestamp: datetime = api_timestamp_string_to_datetime(book_data['updated_at'])
        book = Node(book_data.get('name'), shelf, book_data.get('id'), last_edit_timestamp)
        debug(f"Book: \"{book.get_name()}\", ID: {book.get_id()}")
        books[book.get_id()] = book

info("Getting info about Books not belonging to any shelf")

for book_data in api_get_listing('books'):
    if book_data.get('id') in books.keys():
        continue

    last_edit_timestamp: datetime = api_timestamp_string_to_datetime(book_data['updated_at'])
    book = Node(book_data.get('name'), None, book_data.get('id'), last_edit_timestamp)

    debug(f"Book: \"{book.get_name()}\", ID: {book.get_id()}, last edit: {book.get_last_edit_timestamp()}")
    info(f"Book \"{book.get_name()} has no shelf assigned.\"")
    books[book.get_id()] = book

info("Getting info about Chapters")

for chapter_data in api_get_listing('chapters'):
    last_edit_timestamp: datetime = api_timestamp_string_to_datetime(chapter_data['updated_at'])
    chapter = Node(chapter_data.get('name'),
                   books.get(chapter_data.get('book_id')),
                   chapter_data.get('id'),
                   last_edit_timestamp)
    debug(f"Chapter: \"{chapter.get_name()}\", ID: {chapter.get_id()}, last edit: {chapter.get_last_edit_timestamp()}")
    chapters[chapter.get_id()] = chapter

info("Getting info about Pages")

for page_data in api_get_listing('pages'):
    parent_id = page_data.get('chapter_id')

    last_edit_timestamp: datetime = api_timestamp_string_to_datetime(page_data['updated_at'])

    if parent_id not in chapters.keys():
        parent = books.get(page_data.get('book_id'))
        page = Node(page_data.get('name'), parent, page_data.get('id'), last_edit_timestamp)

        info(f"Page \"{page.get_name()}\" is not in any chapter, "
             f"using Book \"{parent.get_name()}\" as a parent.")

        debug(f"Page: \"{page.get_name()}\", ID: {page.get_id()}, last edit: {page.get_last_edit_timestamp()}")
        pages[page.get_id()] = page
        pages_not_in_chapter[page.get_id()] = page
        continue

    page = Node(page_data.get('name'), chapters.get(parent_id), page_data.get('id'), last_edit_timestamp)
    debug(f"Page: \"{page.get_name()}\", ID: {page.get_id()}, last edit: {page.get_last_edit_timestamp()}")
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
