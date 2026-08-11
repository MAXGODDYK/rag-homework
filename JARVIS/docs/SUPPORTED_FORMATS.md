# Supported ingestion formats

| Family | Extensions | Citation location |
|---|---|---|
| PDF | `.pdf` | page |
| Word | `.docx` | heading/table |
| Slides | `.pptx` | slide/page |
| Spreadsheets | `.xlsx` | sheet and cell range |
| OpenDocument | `.odt`, `.ods`, `.odp` | heading/unit |
| E-books | `.epub` | document heading |
| Web/text | `.html`, `.txt`, `.md`, `.rst` | heading/chunk |
| Data/config | `.csv`, `.tsv`, `.json`, `.jsonl`, `.xml`, `.yaml`, `.toml`, `.ini` | chunk/line |
| Notebooks | `.ipynb` | code or markdown cell |
| Source code | Python, JS/TS, C#, Java, Kotlin, Go, Rust, C/C++, PHP, Ruby, Swift, Dart, Lua, SQL, shell, Docker/Make/protobuf and generic text | exact line range |
| Archives | ZIP, TAR, TAR.GZ/TGZ, 7z, RAR | inner file location |

PDF without a text layer returns an explicit OCR-required error. Images,
audio and video are reserved for later plugins. Unknown text formats use
encoding detection and a line-aware fallback; binaries are rejected.
