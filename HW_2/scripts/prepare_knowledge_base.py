import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment

PROJECT_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_DIR / "data" / "raw"
OUTPUT_DIR = PROJECT_DIR / "data" / "processed"
NORMALIZED_OUTPUT_PATH = (
    OUTPUT_DIR / "normalized_documents.jsonl"
)
EXPECTED_FILES_COUNT = 3
NOISE_TAGS = (
    "script",
    "style",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "svg",
    "noscript",
)
ARTICLE_SELECTORS = {
    "exam_time_planning.html": "div.editor-content",
    "student_daily_routine.html": "div#article div.timg",
    "student_time_management.html": (
        "section.article-intro div.wprt-container"
    ),
}
SEMANTIC_TAGS = ("h1", "h2", "h3", "h4", "p", "li")
EXCLUDED_TEXTS = {
    "student_time_management.html": {
        "Максим Довгай",
    },
}
TIME_MANAGEMENT_HEADINGS = (
    "Створіть розклад.",
    "Пріоритезуйте завдання.",
    "Використовуйте техніки планування.",
    "Заплануйте перерви.",
    "Будьте гнучкими.",
    "Не забувайте про відпочинок.",
)
ACCESS_DATE = "2026-07-20"
SOURCE_METADATA = {
    "exam_time_planning.html": {
        "document_id": "exam_time_planning",
        "title": "Як розпланувати час, готуючись до іспиту?",
        "source_url": (
            "https://mon.gov.ua/news/"
            "yak-rozplanuvati-chas-gotuyuchis-do-ispitu?=print"
        ),
    },
    "student_daily_routine.html": {
        "document_id": "student_daily_routine",
        "title": (
            "Основні кроки ефективної організації "
            "режиму дня студента"
        ),
        "source_url": (
            "https://www.wunu.edu.ua/student-life/"
            "laboratory-psychological-services/"
            "recommendations-and-tips/"
            "9612-osnovni-kroky-efektyvnoi-"
            "organizacii-rezhymu-dnia-studenta.html"
        ),
    },
    "student_time_management.html": {
        "document_id": "student_time_management",
        "title": '"Хакни" свій час',
        "source_url": "https://ugi.edu.ua/hakny-svij-chas/",
    },
}
REQUIRED_DOCUMENT_FIELDS = {
    "document_id",
    "source_file",
    "source_url",
    "title",
    "text",
    "sections",
    "language",
    "domain",
    "document_type",
    "accessed_at",
}

REQUIRED_CHUNK_FIELDS = {
    "chunk_id",
    "document_id",
    "source_file",
    "source_url",
    "chunk_index",
    "text",
    "metadata",
}

REQUIRED_CHUNK_METADATA_FIELDS = {
    "title",
    "section",
    "language",
    "domain",
    "document_type",
    "source_type",
    "accessed_at",
}
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
MIN_CHUNK_SIZE = 500
MAX_CHUNK_SIZE = 1000

CHUNKS_OUTPUT_PATH = OUTPUT_DIR / "chunks.jsonl"

def find_html_files(directory):
    html_files = sorted(directory.glob("*.html"))

    if len(html_files) != EXPECTED_FILES_COUNT:
        raise RuntimeError(
            f"Ожидалось файлов: {EXPECTED_FILES_COUNT}, "
            f"найдено: {len(html_files)}"
        )

    return html_files


def load_html(path):
    html_bytes = path.read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    return soup

def clean_html(soup):
    noise_elements = soup.find_all(NOISE_TAGS)

    for element in noise_elements:
        element.decompose()

    comments = soup.find_all(
        string=lambda value: isinstance(value, Comment)
    )

    for comment in comments:
        comment.extract()

    return soup, len(noise_elements), len(comments)

def normalize_text(text):
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def extract_article(soup, file_name):
    selector = ARTICLE_SELECTORS.get(file_name)

    if selector is None:
        raise ValueError(
            f"Для файла {file_name} отсутствует CSS-селектор"
        )

    article = soup.select_one(selector)

    if article is None:
        raise ValueError(
            f"Не найден контейнер {selector} в файле {file_name}"
        )

    return article

def extract_blocks(article):
    blocks = []

    for element in article.find_all(SEMANTIC_TAGS):
        semantic_parent = element.find_parent(SEMANTIC_TAGS)

        if semantic_parent is not None:
            continue

        text = normalize_text(
            element.get_text(" ", strip=True)
        )

        if not text:
            continue

        if element.name == "li":
            text = f"- {text}"

        blocks.append({
            "tag": element.name,
            "text": text,
        })

    if not blocks:
        raise ValueError("В статье не найдены смысловые блоки")

    return blocks

def filter_blocks(blocks, file_name):
    excluded = EXCLUDED_TEXTS.get(file_name, set())

    filtered_blocks = [
        block
        for block in blocks
        if block["text"] not in excluded
    ]

    return filtered_blocks

def build_daily_routine_sections(blocks):
    sections = []
    current_section = None

    for block in blocks:
        match = re.match(
            r"^КРОК\s+(\d+)\.\s*(.*)$",
            block["text"],
            flags=re.IGNORECASE,
        )

        if match:
            section_number = match.group(1)
            remaining_text = match.group(2).strip()

            current_section = {
                "title": f"КРОК {section_number}",
                "paragraphs": [],
            }

            sections.append(current_section)

            if remaining_text:
                current_section["paragraphs"].append(
                    remaining_text
                )

        elif current_section is not None:
            current_section["paragraphs"].append(
                block["text"]
            )

    if not sections:
        raise ValueError("Не найдены разделы КРОК")

    return sections

def build_exam_sections(blocks):
    sections = [
        {
            "title": "Вступ",
            "paragraphs": [],
        }
    ]

    current_section = sections[0]
    index = 0

    while index < len(blocks):
        block_text = blocks[index]["text"]

        match = re.fullmatch(
            r"Порада\s*№\s*(\d+)",
            block_text,
            flags=re.IGNORECASE,
        )

        if match:
            section_number = match.group(1)
            section_title = f"Порада №{section_number}"

            if index + 1 < len(blocks):
                subtitle = blocks[index + 1]["text"]

                if len(subtitle) <= 120:
                    section_title += f": {subtitle}"
                    index += 1

            current_section = {
                "title": section_title,
                "paragraphs": [],
            }

            sections.append(current_section)

        else:
            current_section["paragraphs"].append(
                block_text
            )

        index += 1

    if len(sections) != 5:
        raise ValueError(
            f"Ожидалось 5 разделов МОН, найдено: {len(sections)}"
        )

    return sections

def build_time_management_sections(blocks):
    sections = [
        {
            "title": "Вступ",
            "paragraphs": [],
        }
    ]

    current_section = sections[0]

    for block in blocks:
        block_text = block["text"]

        heading = next(
            (
                candidate
                for candidate in TIME_MANAGEMENT_HEADINGS
                if block_text.startswith(candidate)
            ),
            None,
        )

        if heading is not None:
            remaining_text = block_text[
                len(heading):
            ].strip()

            current_section = {
                "title": heading.rstrip("."),
                "paragraphs": [],
            }

            sections.append(current_section)

            if remaining_text:
                current_section["paragraphs"].append(
                    remaining_text
                )

        elif block_text.startswith("Загалом,"):
            current_section = {
                "title": "Висновок",
                "paragraphs": [block_text],
            }

            sections.append(current_section)

        else:
            current_section["paragraphs"].append(
                block_text
            )

    if len(sections) != 8:
        raise ValueError(
            f"Ожидалось 8 разделов УГІ, найдено: {len(sections)}"
        )

    return sections

def finalize_sections(sections):
    finalized_sections = []

    for section in sections:
        section_text = "\n\n".join(
            section["paragraphs"]
        ).strip()

        if not section_text:
            continue

        finalized_sections.append({
            "title": section["title"],
            "text": section_text,
        })

    if not finalized_sections:
        raise ValueError(
            "После нормализации не осталось разделов"
        )

    return finalized_sections


def build_document(file_path, sections):
    metadata = SOURCE_METADATA.get(file_path.name)

    if metadata is None:
        raise ValueError(
            f"Нет metadata для {file_path.name}"
        )

    document_text = "\n\n".join(
        f"{section['title']}\n{section['text']}"
        for section in sections
    )

    source_file = file_path.relative_to(
        PROJECT_DIR
    ).as_posix()

    return {
        "document_id": metadata["document_id"],
        "source_file": source_file,
        "source_url": metadata["source_url"],
        "title": metadata["title"],
        "text": document_text,
        "sections": sections,
        "language": "uk",
        "domain": "student_personal_planning",
        "document_type": "web_article",
        "accessed_at": ACCESS_DATE,
    }

def build_sections(blocks, file_name):
    if file_name == "exam_time_planning.html":
        return build_exam_sections(blocks)

    if file_name == "student_daily_routine.html":
        return build_daily_routine_sections(blocks)

    if file_name == "student_time_management.html":
        return build_time_management_sections(blocks)

    raise ValueError(
        f"Неизвестный источник: {file_name}"
    )

def write_jsonl(output_path, records):
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as output_file:
        for record in records:
            json_line = json.dumps(
                record,
                ensure_ascii=False,
            )

            output_file.write(json_line + "\n")

def validate_documents(documents):
    if len(documents) != EXPECTED_FILES_COUNT:
        raise ValueError(
            f"Ожидалось документов: {EXPECTED_FILES_COUNT}, "
            f"получено: {len(documents)}"
        )

    document_ids = set()

    for document in documents:
        missing_fields = (
            REQUIRED_DOCUMENT_FIELDS - set(document)
        )

        if missing_fields:
            raise ValueError(
                f"В документе {document.get('document_id')} "
                f"нет полей: {sorted(missing_fields)}"
            )

        document_id = document["document_id"]

        if document_id in document_ids:
            raise ValueError(
                f"Повторяющийся document_id: {document_id}"
            )

        document_ids.add(document_id)

        if not document["text"].strip():
            raise ValueError(
                f"Пустой текст: {document_id}"
            )

        if not document["sections"]:
            raise ValueError(
                f"Нет разделов: {document_id}"
            )

        if document["language"] != "uk":
            raise ValueError(
                f"Неверный язык: {document_id}"
            )

def split_document_into_units(document):
    units = []

    for section in document["sections"]:
        paragraphs = section["text"].split("\n\n")

        for paragraph in paragraphs:
            sentences = re.split(
                r"(?<=[.!?…])\s+",
                paragraph,
            )

            for sentence_index, sentence in enumerate(
                sentences
            ):
                sentence = sentence.strip()

                if not sentence:
                    continue

                units.append({
                    "section": section["title"],
                    "text": sentence,
                    "paragraph_start": sentence_index == 0,
                })

    if not units:
        raise ValueError(
            f"Нет единиц текста: {document['document_id']}"
        )

    return units

def join_units(units):
    if not units:
        return ""

    result = units[0]["text"]

    for unit in units[1:]:
        if unit["paragraph_start"]:
            separator = "\n\n"
        else:
            separator = " "

        result += separator + unit["text"]

    return result

def get_unit_sections(units):
    section_names = [
        unit["section"]
        for unit in units
    ]

    return list(dict.fromkeys(section_names))

def render_chunk_text(document, units):
    section_names = get_unit_sections(units)
    section_label = " / ".join(section_names)
    body = join_units(units)

    return (
        f"Назва: {document['title']}\n"
        f"Розділ: {section_label}\n\n"
        f"{body}"
    )

def find_overlap_start(units, chunk_start, chunk_end):
    overlap_start = chunk_end

    while overlap_start > chunk_start:
        overlap_start -= 1

        overlap_text = join_units(
            units[overlap_start:chunk_end]
        )

        if len(overlap_text) >= CHUNK_OVERLAP:
            break

    if overlap_start <= chunk_start:
        return chunk_start + 1

    return overlap_start

def build_draft_chunks(document, units):
    draft_chunks = []
    start_index = 0

    while start_index < len(units):
        end_index = start_index

        while end_index < len(units):
            candidate_units = units[start_index:end_index + 1]

            candidate_text = render_chunk_text(document, candidate_units,)

            if (
                end_index > start_index
                and len(candidate_text) > CHUNK_SIZE
            ):
                break

            end_index += 1

        chunk_units = units[start_index:end_index]

        if not chunk_units:
            raise ValueError(
                f"Не удалось собрать chunk: "
                f"{document['document_id']}"
            )
        draft_chunks.append(chunk_units)

        if end_index >= len(units):
            break

        next_start = find_overlap_start(units, start_index, end_index,)

        if next_start <= start_index:
            raise RuntimeError(
                f"Chunking не продвигается: "
                f"{document['document_id']}"
            )

        start_index = next_start

    return draft_chunks

def build_chunk_records(document, draft_chunks):
    chunk_records = []

    for chunk_index, chunk_units in enumerate(
        draft_chunks,
        start=1,
    ):
        section_names = get_unit_sections(chunk_units)
        section_label = " / ".join(section_names)

        chunk_record = {
            "chunk_id": (
                f"{document['document_id']}"
                f"_chunk_{chunk_index:03d}"
            ),
            "document_id": document["document_id"],
            "source_file": document["source_file"],
            "source_url": document["source_url"],
            "chunk_index": chunk_index,
            "text": render_chunk_text(
                document,
                chunk_units,
            ),
            "metadata": {
                "title": document["title"],
                "section": section_label,
                "language": document["language"],
                "domain": document["domain"],
                "document_type": document["document_type"],
                "source_type": "html",
                "accessed_at": document["accessed_at"],
            },
        }

        chunk_records.append(chunk_record)

    return chunk_records

def validate_chunks(chunks):
    if not chunks:
        raise ValueError("Список chunks пуст")

    chunk_ids = set()
    next_indexes = {}

    for chunk in chunks:
        missing_fields = (
            REQUIRED_CHUNK_FIELDS - set(chunk)
        )

        if missing_fields:
            raise ValueError(
                f"В chunk нет полей: {sorted(missing_fields)}"
            )

        document_id = chunk["document_id"]
        chunk_index = chunk["chunk_index"]
        chunk_id = chunk["chunk_id"]

        if chunk_id in chunk_ids:
            raise ValueError(
                f"Повторяющийся chunk_id: {chunk_id}"
            )

        chunk_ids.add(chunk_id)

        expected_index = next_indexes.get(document_id, 1)

        if chunk_index != expected_index:
            raise ValueError(
                f"Нарушена нумерация {document_id}: "
                f"ожидался {expected_index}, "
                f"получен {chunk_index}"
            )

        next_indexes[document_id] = expected_index + 1

        expected_id = (
            f"{document_id}_chunk_{chunk_index:03d}"
        )

        if chunk_id != expected_id:
            raise ValueError(
                f"Неверный chunk_id: {chunk_id}"
            )

        text_length = len(chunk["text"])

        if not MIN_CHUNK_SIZE <= text_length <= MAX_CHUNK_SIZE:
            raise ValueError(
                f"Недопустимая длина {chunk_id}: "
                f"{text_length}"
            )

        metadata = chunk["metadata"]

        if not isinstance(metadata, dict):
            raise ValueError(
                f"metadata должен быть объектом: {chunk_id}"
            )

        missing_metadata = (
            REQUIRED_CHUNK_METADATA_FIELDS - set(metadata)
        )

        if missing_metadata:
            raise ValueError(
                f"В metadata {chunk_id} нет полей: "
                f"{sorted(missing_metadata)}"
            )

        if metadata["language"] != "uk":
            raise ValueError(
                f"Неверный язык: {chunk_id}"
            )

        if metadata["source_type"] != "html":
            raise ValueError(
                f"Неверный source_type: {chunk_id}"
            )

def main():
    html_files = find_html_files(INPUT_DIR)
    documents = []
    all_chunks = []

    for file_path in html_files:
        soup = load_html(file_path)
        soup, _, _ = clean_html(soup)

        article = extract_article(
            soup,
            file_path.name,
        )

        blocks = extract_blocks(article)
        blocks = filter_blocks(
            blocks,
            file_path.name,
        )

        sections = build_sections(
            blocks,
            file_path.name,
        )

        sections = finalize_sections(sections)

        document = build_document(
            file_path,
            sections,
        )

        documents.append(document)

        units = split_document_into_units(document)

        draft_chunks = build_draft_chunks(
            document,
            units,
        )
        chunk_records = build_chunk_records(
            document,
            draft_chunks,
        )

        all_chunks.extend(chunk_records)

        chunk_lengths = [
            len(render_chunk_text(document, chunk_units))
            for chunk_units in draft_chunks
        ]

        print(
            document["document_id"],
            "draft chunks:",
            len(draft_chunks),
            "lengths:",
            chunk_lengths,
        )

    validate_documents(documents)
    validate_chunks(all_chunks)

    print("Проверка документов: OK")
    print("Проверка chunks: OK")

    write_jsonl(
        NORMALIZED_OUTPUT_PATH,
        documents,
    )

    write_jsonl(
        CHUNKS_OUTPUT_PATH,
        all_chunks,
    )

    print(
        "Нормализованные документы записаны:",
        NORMALIZED_OUTPUT_PATH,
    )

    print(
        "Chunks записаны:",
        CHUNKS_OUTPUT_PATH,
    )

    print("Всего документов:", len(documents))
    print("Всего chunks:", len(all_chunks))


if __name__ == "__main__":
    main()