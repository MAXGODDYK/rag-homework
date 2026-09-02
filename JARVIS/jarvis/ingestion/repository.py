from __future__ import annotations

import re
from pathlib import Path

from .models import GraphEdgeRecord, SymbolRecord


EXTENSION_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "javascript",
    ".cs": "c_sharp",
    ".java": "java",
    ".kt": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    # Project headers are parsed as C++ because JARVIS primarily indexes
    # repository code and C++ headers commonly contain classes, namespaces and
    # framework macros (for example Unreal's UCLASS/GENERATED_BODY). Feeding
    # those headers to the C grammar can corrupt the native tree-sitter parser
    # state instead of returning an ordinary parse error.
    ".h": "cpp",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".dart": "dart",
    ".lua": "lua",
    ".sql": "sql",
    ".ps1": "powershell",
    ".sh": "bash",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}

SYMBOL_TYPES = {
    "function_definition": "function",
    "function_declaration": "function",
    "method_definition": "method",
    "method_declaration": "method",
    "class_definition": "class",
    "class_declaration": "class",
    "interface_declaration": "interface",
    "struct_item": "struct",
    "struct_specifier": "struct",
    "enum_declaration": "enum",
    "enum_item": "enum",
}

# tree-sitter-language-pack 1.16.1 can terminate the Python process with an
# access violation while walking macro-heavy Unreal C++ translation units.
# A native crash cannot be caught, so use the deterministic regex analyzer for
# C++ until that parser is safe for these files. Retrieval still indexes the
# complete source text; only optional symbol enrichment uses this fallback.
UNSAFE_NATIVE_PARSER_LANGUAGES = frozenset({"cpp"})

IMPORT_PATTERNS = [
    re.compile(r"^\s*(?:from\s+([\w.]+)\s+)?import\s+([\w.*]+)", re.MULTILINE),
    re.compile(r"^\s*import\s+(?:[^'\"]+\s+from\s+)?['\"]([^'\"]+)['\"]", re.MULTILINE),
    re.compile(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE),
    re.compile(r"^\s*#include\s*[<\"]([^>\"]+)[>\"]", re.MULTILINE),
    re.compile(r"^\s*use\s+([\w:]+)", re.MULTILINE),
]


def language_for_path(path: Path) -> str | None:
    return EXTENSION_LANGUAGE.get(path.suffix.lower())


def _node_name(node, source: bytes) -> str | None:
    for child in node.children:
        if child.type in {"identifier", "type_identifier", "name", "property_identifier"}:
            return source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
    return None


def analyze_code(path: Path, text: str) -> tuple[list[SymbolRecord], list[GraphEdgeRecord]]:
    language = language_for_path(path)
    symbols: list[SymbolRecord] = []
    if language and language not in UNSAFE_NATIVE_PARSER_LANGUAGES:
        try:
            from tree_sitter_language_pack import get_parser

            parser = get_parser(language)
            source = text.encode("utf-8")
            tree = parser.parse(source)
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                kind = SYMBOL_TYPES.get(node.type)
                if kind:
                    name = _node_name(node, source)
                    if name:
                        symbols.append(
                            SymbolRecord(
                                name=name,
                                kind=kind,
                                line_start=node.start_point.row + 1,
                                line_end=node.end_point.row + 1,
                                metadata={"language": language, "node_type": node.type},
                            )
                        )
                stack.extend(reversed(node.children))
        except Exception:
            # Generic regex fallback remains mandatory for unsupported/broken grammars.
            symbols = []

    if not symbols:
        if language == "cpp":
            # Account for `enum class` and Unreal-style export macros such as
            # `class MYPROJECT_API AGameplayCharacterBase`.
            expression = (
                r"^\s*(?:class|struct|enum(?:\s+class)?)\s+"
                r"(?:(?:[A-Za-z_]\w*_API)\s+)?([A-Za-z_]\w*)"
            )
        else:
            expression = (
                r"^\s*(?:class|interface|struct|enum|def|function|func|fn)\s+"
                r"([A-Za-z_$][\w$]*)"
            )
        fallback = re.compile(expression, re.MULTILINE)
        lines = text.splitlines()
        for match in fallback.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            symbols.append(
                SymbolRecord(
                    name=match.group(1),
                    kind="symbol",
                    line_start=line,
                    line_end=min(line + 1, max(1, len(lines))),
                    metadata={"language": language or "unknown", "parser": "fallback"},
                )
            )

    targets: set[str] = set()
    for pattern in IMPORT_PATTERNS:
        for match in pattern.finditer(text):
            for group in match.groups():
                if group:
                    targets.add(group)
    edges = [GraphEdgeRecord(target_ref=target, edge_type="imports") for target in sorted(targets)]
    return symbols, edges
