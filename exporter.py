import argparse
import json
import logging
import os
from datetime import datetime
from logging import info, error, debug
from pathlib import Path
import re
import sys
import ssl
from typing import Dict, List, Union
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import urllib.parse
import base64
from time import time
from time import sleep

# Ignore Self Signed Certificates
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# (formatName, fileExtension)
FORMATS: Dict['str', 'str'] = {
    'markdown': 'md',
    'plaintext': 'txt',
    'pdf': 'pdf',
    'html': 'html',
    'zip': 'zip'
}

LEVELS = ['pages', 'chapters', 'books']

LOG_LEVEL: Dict = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR
}

# Characters in filenames to be replaced with "_"
FORBIDDEN_CHARS: List[str] = ["/", "#"]

parser = argparse.ArgumentParser(description='BookStack exporter')
parser.add_argument('-p',
                    '--path',
                    type=str,
                    default='.',
                    help='Path where exported files will be placed.')
parser.add_argument(
    '-t',
    '--token-file',
    type=str,
    default=f'.{os.path.sep}token.txt',
    help='File containing authorization token in format TOKEN_ID:TOKEN_SECRET')
parser.add_argument(
    '-H',
    '--host',
    type=str,
    default='https://localhost',
    help='Your domain with protocol prefix, example: https://example.com')
parser.add_argument('-f',
                    '--formats',
                    type=str,
                    default=['markdown'],
                    nargs="+",
                    help='Space separated list of formats to use for export.',
                    choices=FORMATS.keys())
parser.add_argument('--rate-limit',
                    type=int,
                    default=180,
                    help='How many api requests can be made in a minute. '
                    'Default is 180 (BookStack defaults)')
parser.add_argument('-c',
                    '--forbidden-chars',
                    type=str,
                    default=FORBIDDEN_CHARS,
                    nargs="+",
                    help='Space separated list of symbols to be replaced '
                    'with "_" in filenames.')
parser.add_argument('-u',
                    '--user-agent',
                    type=str,
                    default="BookStack exporter",
                    help='User agent header content. In situations'
                    ' where requests are blocked because of bad client/'
                    'unrecognized web browser/etc (like with CloudFlare'
                    ' tunnels), change to some typical '
                    'web browser user agent header.')
parser.add_argument('--additional-headers',
                    type=str,
                    nargs="+",
                    default=[],
                    help='List of arbitrary additional HTTP headers to be '
                    'sent with every HTTP request. They can override default'
                    ' ones, including Authorization header. IMPORTANT: '
                    'these headers are also sent when downloading external '
                    'attachments! Don\'t put here any private data.'
                    'Example: -u "Header1: value1" "Header2: value2"')
parser.add_argument(
    '-l',
    '--level',
    type=str,
    default=['pages'],
    nargs="+",
    help="Space separated list of levels at which should be export "
    "performed. ",
    choices=LEVELS)
parser.add_argument(
    '--force-update-files',
    action='store_true',
    default=False,
    help="Set this option to skip checking local files timestamps against "
    "remote last edit timestamps. This will cause overwriting local files,"
    " even if they seem to be already in newest version.")
parser.add_argument(
    '--images',
    action='store_true',
    default=False,
    help="Download images and place them in dedicated directory in export path"
    " root, preserving their internal paths")
parser.add_argument(
    '--markdown-images',
    action='store_true',
    default=False,
    help="The same as --images, but will also update image links in "
    "exported markdown files (if they are bein exported)."
    " Warning: this is experimental, as API does not provide a way to "
    "know what images are actually on the page. Therefore for markdown data"
    " all ']({URL}' occurences will be replaced with local, relative "
    "path to images, and additionally any '/scaled-\\d+-/' regex match"
    " will be replaced with '/' so that scaled images are also displayed")
parser.add_argument('--images-dir',
                    type=str,
                    default="exported-images",
                    help='When exporting images, they will be organized in'
                    ' directory located at the same path as exported document.'
                    ' This parameter defines name of this directory.')
parser.add_argument('--skip-broken-image-links',
                    default=False,
                    action='store_true',
                    help="Don't fail and skip downloading images if their "
                    "url obtained from images gallery API seem broken "
                    "(image cannot be downloaded OR fails to download).")
parser.add_argument('--dont-export-attachments',
                    default=False,
                    action='store_true',
                    help="Set this to prevent exporting any attachments.")
parser.add_argument(
    '--dont-export-external-attachments',
    action='store_true',
    default=False,
    help="Set this to prevent exporting external attachments (from links).")
parser.add_argument('-V',
                    '--log-level',
                    type=str,
                    default='info',
                    help='Set verbosity level.',
                    choices=LOG_LEVEL.keys())

args = parser.parse_args()


def removesuffix(text, suffix):
    """Remove suffix from text if matched."""
    if text.endswith(suffix):
        return text[:len(text) - len(suffix)]
    return text


logging.basicConfig(format='%(levelname)s :: %(message)s',
                    level=LOG_LEVEL.get(args.log_level))

formats: List[str] = args.formats
FORBIDDEN_CHARS = args.forbidden_chars

for frmt in formats:
    if frmt not in FORMATS:
        error("Unknown format name (NOT file extension), "
              "check api docs for current version of your BookStack")
        sys.exit(1)

API_PREFIX: str = f"{removesuffix(args.host, os.path.sep)}/api"
FS_PATH: str = removesuffix(args.path, os.path.sep)
LEVEL_CHOICE: List[str] = args.level
for lvl in LEVEL_CHOICE:
    if lvl not in LEVELS:
        error(f"Level {lvl} is not supported, can be only one of {LEVELS}")
        sys.exit(1)

with open(args.token_file, 'r', encoding='utf-8') as f:
    TOKEN: str = removesuffix(f.readline(), '\n')

HEADERS = {
    'Content-Type': 'application/json; charset=utf-8',
    'Authorization': f"Token {TOKEN}",
    'User-Agent': args.user_agent
}
HEADERS_NO_TOKEN = {
    'Content-Type': 'application/json; charset=utf-8',
    'User-Agent': args.user_agent
}

for header in args.additional_headers:
    values = header.split(':', 1)
    if len(values) < 2:
        raise ValueError(f"Improper HTTP header specification: {header}")
    HEADERS[values[0]] = values[1]
    HEADERS_NO_TOKEN[values[0]] = values[1]

SKIP_TIMESTAMPS: bool = args.force_update_files
SKIP_BROKEN_IMAGE_LINKS: bool = args.skip_broken_image_links


class ApiRateLimiter:

    def __init__(self, rate_limit: int) -> None:
        self.__rate_limit = rate_limit
        info(f"API rate limit: {self.__rate_limit}/min")
        self.__requests_times: List[float] = []

    def limit_rate_request(self):
        """Count another request and wait minimal required time if limit is reached."""
        current_time = time()
        self.__requests_times.append(current_time)
        # filter out requests older than 60s ago
        self.__requests_times = list(
            filter(lambda x: current_time - x <= 60, self.__requests_times))

        # sleep until oldest remembered request is more than 60s ago
        if len(self.__requests_times) > self.__rate_limit:
            wait_time = self.__requests_times[0] + 60 - current_time
            info(f"API Rate limit reached, waiting {round(wait_time, 2)}s")
            sleep(wait_time)


api_rate_limiter = ApiRateLimiter(args.rate_limit)


class Node:
    """Clas representing any node in whole bookstack documents "tree"."""

    def __init__(self, name: str, parent: Union['Node', None], node_id: int,
                 last_edit_timestamp: datetime):
        for char in FORBIDDEN_CHARS:
            name = name.replace(char, "_")
        self.__name: str = name
        self.__children: List['Node'] = []

        self.__parent: Union['Node', None] = parent
        if parent is not None:
            parent.add_child(self)

        self.__last_edit_timestamp: datetime = last_edit_timestamp
        self.__node_id = node_id

    @property
    def name(self) -> str:
        """Return name of this Shelf/Book/Chapter/Page."""
        return self.__name

    @property
    def parent(self) -> Union['Node', None]:
        """Return parent Node or None if there isn't any."""
        return self.__parent

    def changed_since(self, timestamp: datetime) -> int:
        """
        Check if remote version have changed after given timestamp,
        including its children
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

    def get_all_ids(self) -> List[int]:
        """Return list containing id of this node, and all child nodes."""
        ids = [self.get_id()]
        for child in self.__children:
            child_ids = child.get_all_ids()
            for id in child_ids:
                ids.append(id)
        return ids

    def get_path(self) -> str:
        if self.__parent is None:
            return "."
        return self.__parent.get_path() + os.path.sep + self.__parent.name

    def get_id(self) -> int:
        return self.__node_id

    def parents_levels(self) -> int:
        """Calculate nesting level of this Node."""
        if self.__parent is not None:
            return 1 + self.__parent.parents_levels()
        return 0


class AttachedFile(Node):

    def __init__(self, name: str, parent_id: int, url: str, path: str,
                 node_id: int, last_edit_timestamp: datetime):
        """
        name: filename
        parent_id: uploaded_to value from api
        url: http url directly for file download
        path: path value of the object from api (filepath)
        node_id: id of the object
        last_edit_timestamp: timestamp from updated_at api field
        """
        super().__init__(name, None, node_id, last_edit_timestamp)
        self.__parent_id = parent_id
        self.__url = url
        self.__path = path

    def get_parent_id(self) -> int:
        return self.__parent_id

    def get_url(self) -> str:
        return self.__url

    def get_path(self) -> str:
        """Path value of the object from api."""
        return self.__path


shelves: Dict[int, Node] = {}
books: Dict[int, Node] = {}
chapters: Dict[int, Node] = {}
pages: Dict[int, Node] = {}
pages_not_in_chapter: Dict[int, Node] = {}
attachments: Dict[int, Node] = {}
images: Dict[int, AttachedFile] = {}


def api_timestamp_string_to_datetime(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')


def make_dir(path: str):
    path_obj = Path(path)
    if path_obj.exists():
        return
    info(f"Creating dir {path}")
    path_obj.mkdir(exist_ok=True, parents=True)


def api_get_bytes(path: str, raw_url: bool = False, **kwargs) -> bytes:
    """
    Retrieve bytes on specific relative api path.

    If raw_url is set to true, it will be accessed directly, without
    prefixing with base api url.
    """
    request_path: str = f'{API_PREFIX}/{path}'
    if raw_url:
        request_path = path

    if len(kwargs) > 0:
        params: str = urllib.parse.urlencode(kwargs)
        request_path += f"?{params}"

    debug(f"Making http request: {request_path}")

    request: Request = Request(request_path, headers=HEADERS)

    api_rate_limiter.limit_rate_request()
    with urlopen(request, context=ctx) as response:
        if response.status == 403:
            error("403 Forbidden, check your token!")
            sys.exit(response.status)

        return response.read()


def api_get_dict(path: str) -> dict:
    """Make api request at specified path and return result as dict."""
    data = api_get_bytes(path).decode()
    return json.loads(data)


def api_get_listing(path: str) -> list:
    """Retrieve whole lists through api.

    Request for another 50 until have collected "total" amount.
    :param path:
    :return:
    """
    count: int = 50
    total: int = count

    result: list = []

    while total > len(result):
        data: dict = json.loads(
            api_get_bytes(path, count=count, offset=len(result)))
        total = data['total']
        result += data['data']

        debug(f"API listing got {len(result)} items out of maximum {count}")

    return result


def image_translate_path(img_path: str) -> str:
    """Update remote path attribute string to be local image path.

    img_path: image 'path' attribute from api
    """
    return f"{FS_PATH}{os.path.sep}{args.images_dir}{img_path}"


def check_if_update_needed(file_path: str, document: Node) -> bool:
    """Check if a Node need updating on disk, according to timestamps."""
    if SKIP_TIMESTAMPS:
        return True
    debug(f"Checking for update for file {file_path}")

    if not os.path.exists(file_path):
        debug(f"Document {file_path} is missing on disk, update needed.")
        return True
    local_last_edit: datetime = datetime.fromtimestamp(
        os.path.getmtime(file_path))
    remote_last_edit: datetime = document.get_last_edit_timestamp()

    debug("Local file creation timestamp: "
          f"{local_last_edit.date()} {local_last_edit.time()}, "
          "remote edit timestamp:  "
          f"{remote_last_edit.date()} {remote_last_edit.time()}")
    changes: int = document.changed_since(local_last_edit)

    if changes > 0:
        info(f"Document \"{file_path}\" consists of {changes} "
             "outdated documents, update needed.")
        return True

    debug(f"Document \"{file_path}\" consists of {changes} "
          "outdated documents, skipping updating.")
    return False


def update_markdown_image_tags(doc: Node, data: bytes) -> bytes:
    """Update all image tags to point to exported images in given markdown data."""
    levels = doc.parents_levels()
    # "](" is a part of markdown image tag, used here to
    # try preventing replacing host url in other paces
    dir_fallback = ']('
    dir_fallback += '../' * levels

    host = removesuffix(args.host, '/')
    dir_fallback += args.images_dir
    data = data.replace(f']({host}'.encode(), dir_fallback.encode())
    data_str = re.sub(r'/scaled-\d+-/', r'/', data.decode())
    return data_str.encode()


def export_doc(documents: List[Node], level: str):
    """Save document-like Nodes to files."""
    for document in documents:
        make_dir(f"{FS_PATH}{os.path.sep}{document.get_path()}")

        for v_format in formats:
            path: str = f"{FS_PATH}{os.path.sep}{document.get_path()}" + \
                f"{os.path.sep}{document.name}.{FORMATS[v_format]}"

            if not check_if_update_needed(path, document):
                continue

            data: bytes = api_get_bytes(
                f'{level}/{document.get_id()}/export/{v_format}')
            if args.markdown_images and v_format == 'markdown':
                data = update_markdown_image_tags(document, data)

            with open(path, 'wb') as file:
                info(f"Saving {path}")
                file.write(data)


def export_attachments(attachments: List[Node]):
    """Save attachment Nodes to files."""
    for attachment in attachments:

        base_path = attachment.get_path()
        if attachment.parent is None:
            base_path = f'__ATTACHMENTS_FROM_DELETED_PAGES__{os.path.sep}{base_path}'

        make_dir(f"{FS_PATH}{os.path.sep}{base_path}")

        path: str = f"{FS_PATH}{os.path.sep}{base_path}" + \
            f"{os.path.sep}{attachment.name}"

        if not check_if_update_needed(path, attachment):
            continue

        data = api_get_bytes(f'attachments/{attachment.get_id()}')
        data = json.loads(data)
        content = data['content']
        content_url = urllib.parse.urlparse(content)

        if content_url.scheme:
            if args.dont_export_external_attachments:
                continue
            info(f"Downloading attachment from url: {content_url.geturl()}")
            request: Request = Request(content_url.geturl(),
                                       headers=HEADERS_NO_TOKEN)

            with urlopen(request, context=ctx) as response:
                if response.status >= 300:
                    error(
                        "Could not download link-type attachment from "
                        f"'{content_url.geturl()}, got code {response.status}'!"
                    )
                    sys.exit(response.status)

                with open(path, 'wb') as file:
                    info(f"Saving {path}")
                    file.write(response.read())
        else:
            with open(path, 'wb') as file:
                info(f"Saving {path}")
                file.write(base64.b64decode(content))


def export_images():
    for img in images.values():
        path = image_translate_path(img.get_path())
        img_dir = os.path.dirname(path)
        make_dir(img_dir)

        if not check_if_update_needed(path, img):
            continue

        try:
            data: bytes = api_get_bytes(img.get_url(), raw_url=True)
        except (URLError, HTTPError) as exc:
            error(f"Failed downloading image '{img.get_url()}': {exc}")
            if not SKIP_BROKEN_IMAGE_LINKS:
                sys.exit(1)
            else:
                continue
        with open(path, 'wb') as file:
            info(f"Saving {path}")
            file.write(data)


#########################
# Gathering data from api
#########################

info("Getting info about Shelves and their Books")

for shelf_data in api_get_listing('shelves'):

    last_edit_ts: datetime = api_timestamp_string_to_datetime(
        shelf_data['updated_at'])
    shelf = Node(shelf_data.get('name'), None, shelf_data.get('id'),
                 last_edit_ts)

    debug(f"Shelf: \"{shelf.name}\", ID: {shelf.get_id()}")
    shelves[shelf.get_id()] = shelf

    shelf_details = api_get_dict(f'shelves/{shelf.get_id()}')

    if shelf_details.get('books') is None:
        continue
    for book_data in shelf_details['books']:

        last_edit_ts: datetime = api_timestamp_string_to_datetime(
            book_data['updated_at'])
        book = Node(book_data.get('name'), shelf, book_data.get('id'),
                    last_edit_ts)
        debug(f"Book: \"{book.name}\", ID: {book.get_id()}")
        books[book.get_id()] = book

info("Getting info about Books not belonging to any shelf")

for book_data in api_get_listing('books'):
    if book_data.get('id') in books:
        continue

    last_edit_ts: datetime = api_timestamp_string_to_datetime(
        book_data['updated_at'])
    book = Node(book_data.get('name'), None, book_data.get('id'), last_edit_ts)

    debug(f"Book: \"{book.name}\", ID: {book.get_id()}, "
          f"last edit: {book.get_last_edit_timestamp()}")
    info(f"Book \"{book.name} has no shelf assigned.\"")
    books[book.get_id()] = book

info("Getting info about Chapters")

for chapter_data in api_get_listing('chapters'):
    last_edit_ts: datetime = api_timestamp_string_to_datetime(
        chapter_data['updated_at'])
    chapter = Node(chapter_data.get('name'),
                   books.get(chapter_data.get('book_id')),
                   chapter_data.get('id'), last_edit_ts)
    debug(f"Chapter: \"{chapter.name}\", ID: {chapter.get_id()},"
          f" last edit: {chapter.get_last_edit_timestamp()}")
    chapters[chapter.get_id()] = chapter

info("Getting info about Pages")

for page_data in api_get_listing('pages'):
    parent_id = page_data.get('chapter_id')

    last_edit_ts: datetime = api_timestamp_string_to_datetime(
        page_data['updated_at'])

    if parent_id not in chapters:
        parent = books[page_data['book_id']]
        page = Node(page_data.get('name'), parent, page_data.get('id'),
                    last_edit_ts)

        info(f"Page \"{page.name}\" is not in any chapter, "
             f"using Book \"{parent.name}\" as a parent.")

        debug(f"Page: \"{page.name}\", ID: {page.get_id()},"
              f" last edit: {page.get_last_edit_timestamp()}")
        pages[page.get_id()] = page
        pages_not_in_chapter[page.get_id()] = page
        continue

    page = Node(page_data.get('name'), chapters.get(parent_id),
                page_data.get('id'), last_edit_ts)
    debug(f"Page: \"{page.name}\", ID: {page.get_id()}, "
          f"last edit: {page.get_last_edit_timestamp()}")
    pages[page.get_id()] = page

if not args.dont_export_attachments:
    info("Getting info about Attachments.")

    for attachment_data in api_get_listing('attachments'):
        last_edit_ts: datetime = api_timestamp_string_to_datetime(
            attachment_data['updated_at'])
        all_pages = {}
        all_pages.update(pages)
        all_pages.update(pages_not_in_chapter)
        attachment = Node(attachment_data.get('name'),
                          all_pages.get(attachment_data.get('uploaded_to')),
                          attachment_data.get('id'), last_edit_ts)
        debug(f"Attachment: \"{attachment.name}\", ID: {attachment.get_id()},"
              f" last edit: {attachment.get_last_edit_timestamp()}")
        attachments[attachment.get_id()] = attachment

if args.images or args.markdown_images:
    info("Getting info about Image gallery.")

    for image_data in api_get_listing('image-gallery'):
        last_edit_ts: datetime = api_timestamp_string_to_datetime(
            image_data['updated_at'])
        image = AttachedFile(name=image_data.get('name'),
                             parent_id=image_data.get('uploaded_to'),
                             url=image_data.get('url'),
                             path=image_data.get('path'),
                             node_id=image_data.get('id'),
                             last_edit_timestamp=last_edit_ts)
        debug(f"Image: \"{image.name}\", ID: {image.get_id()},"
              f" last edit: {image.get_last_edit_timestamp()}")
        images[image.get_id()] = image

#########################
# Exporting data from api
#########################

files: List[Node] = []
EXPORT_PAGES_NOT_IN_CHAPTER: bool = False

for lvl in LEVEL_CHOICE:
    if lvl == 'pages':
        files = list(pages.values())
    elif lvl == 'chapters':
        files = list(chapters.values())
        EXPORT_PAGES_NOT_IN_CHAPTER = True
    elif lvl == 'books':
        files = list(books.values())

    export_doc(files, lvl)

if EXPORT_PAGES_NOT_IN_CHAPTER:
    info("Exporting pages that are not in chapter...")
    export_doc(list(pages_not_in_chapter.values()), 'pages')

if not args.dont_export_attachments:
    export_attachments(list(attachments.values()))

if args.images or args.markdown_images:
    export_images()

info("Finished")
sys.exit(0)
