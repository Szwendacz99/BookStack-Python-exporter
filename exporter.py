import argparse
import json
import logging
import os
from logging import info, error
from pathlib import Path
from urllib.request import urlopen, Request

logging.basicConfig(format='%(levelname)s :: %(message)s', level=logging.INFO)

# (formatName, fileExtension)
FORMATS: dict['str', 'str'] = {
    'markdown': 'md',
    'plaintext': 'txt',
    'pdf': 'pdf',
    'html': 'html'
}

parser = argparse.ArgumentParser(description='BookStack exporter')
parser.add_argument('-p', '--path', type=str, default='.',
                    help='Path where exported files will be placed.')
parser.add_argument('-t', '--token-file', type=str, default=f'.{os.path.sep}token.txt',
                    help='File containing authorization token in format TOKEN_ID:TOKEN_SECRET')
parser.add_argument('-H', '--host', type=str, default='https://localhost',
                    help='Your domain with protocol prefix, example: https://example.com')
parser.add_argument('-f', '--formats', type=str, default='md',
                    help=f'Coma separated list of formats to use for export.'
                         f' Available ones: {",".join([f for f in FORMATS.keys()])}')
args = parser.parse_args()

formats = args.formats.split(',')
for frmt in formats:
    if frmt not in FORMATS.keys():
        raise Exception("Unknown format name (NOT file extension), "
                        "check api docs for current version of your BookStack")

API_PREFIX: str = f"{args.host.removesuffix(os.path.sep)}/api"
FS_PATH: str = args.path.removesuffix(os.path.sep)

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
    if book_data.get('id') != 0:
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
    if parent_id == 0:
        parent_id = page_data.get('book_id')
        info(f"Page \"{page_data.get('name')}\" is not in any chapter, "
             f"using Book \"{books.get(parent_id).get_name()}\" as a parent.")
        page = Node(page_data.get('name'), books.get(parent_id), page_data.get('id'))
        pages[page.get_id()] = page
        continue

    page = Node(page_data.get('name'), chapters.get(parent_id), page_data.get('id'))
    pages[page.get_id()] = page

for page in pages.values():
    make_dir(f"{FS_PATH}{os.path.sep}{page.get_path()}")

    for frmt in formats:
        path: str = f"{FS_PATH}{os.path.sep}{page.get_path()}{os.path.sep}{page.get_name()}.{FORMATS[frmt]}"

        data: bytes = api_get_bytes(f'pages/{page.get_id()}/export/{frmt}')
        if os.path.exists(path):
            info(f"Updating file with page \"{page.get_name()}.{FORMATS[frmt]}\"")
        else:
            info(f"Saving new file with page \"{page.get_name()}.{FORMATS[frmt]}\"")
        with open(path, 'wb') as f:
            f.write(data)
