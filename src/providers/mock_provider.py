import re
from src.providers.base import BaseProvider
from src.services.diff_parser import AddedLine
from src.services.chunker import DiffChunk
from src.models.schemas import Finding

MOCK_002_REGEX = re.compile(r"(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", re.IGNORECASE)
MOCK_003_REGEX = re.compile(r"""(['"][^'"]*?\b(?:SELECT|INSERT|UPDATE|DELETE)\b[^'"]*?['"]\s*\+)|(\+\s*['"][^'"]*?\b(?:SELECT|INSERT|UPDATE|DELETE)\b[^'"]*?['"])""", re.IGNORECASE)
MOCK_INJ_REGEX = re.compile(r"(ignore previous instructions|disregard all prior|you are now)", re.IGNORECASE)

def sort_and_dedup_findings(findings: list[Finding]) -> list[Finding]:
    seen_ids = set()
    deduped: list[Finding] = []
    
    for f in findings:
        if f.id not in seen_ids:
            seen_ids.add(f.id)
            deduped.append(f)
            
    deduped.sort(key=lambda f: (f.path, f.line, f.ruleId))
    return deduped

def scan_mock_004(added_lines: list[AddedLine]) -> list[Finding]:
    findings: list[Finding] = []
    i = 0
    while i < len(added_lines):
        line_item = added_lines[i]
        text = line_item.content
        
        catch_match = re.search(r'\bcatch\b', text)
        if catch_match:
            catch_idx = catch_match.start()
            brace_start_line_idx = i
            brace_char_idx = text.find('{', catch_idx)
            
            while brace_char_idx == -1 and brace_start_line_idx + 1 < len(added_lines):
                brace_start_line_idx += 1
                brace_char_idx = added_lines[brace_start_line_idx].content.find('{')
                
            if brace_char_idx != -1:
                brace_depth = 0
                has_content = False
                scan_line_idx = brace_start_line_idx
                start_char_idx = brace_char_idx
                block_closed = False
                
                while scan_line_idx < len(added_lines):
                    line_str = added_lines[scan_line_idx].content
                    ch_start = start_char_idx if scan_line_idx == brace_start_line_idx else 0
                    
                    for ch_idx in range(ch_start, len(line_str)):
                        ch = line_str[ch_idx]
                        if ch == '{':
                            brace_depth += 1
                        elif ch == '}':
                            brace_depth -= 1
                            if brace_depth == 0:
                                block_closed = True
                                break
                        elif brace_depth > 0:
                            if not ch.isspace() and ch not in (';', ','):
                                has_content = True
                                
                    if block_closed:
                        break
                    scan_line_idx += 1
                    start_char_idx = 0
                    
                if block_closed and not has_content:
                    finding_id = f"MOCK-004:{line_item.path}:{line_item.line}"
                    findings.append(Finding(
                        id=finding_id,
                        ruleId="MOCK-004",
                        path=line_item.path,
                        line=line_item.line,
                        severity="high",
                        category="correctness",
                        title="swallowed exception",
                        evidence=line_item.content
                    ))
        i += 1
    return findings

def evaluate_line_rules(line_item: AddedLine) -> list[Finding]:
    findings: list[Finding] = []
    path = line_item.path
    line_no = line_item.line
    text = line_item.content

    if "eval(" in text:
        findings.append(Finding(
            id=f"MOCK-001:{path}:{line_no}",
            ruleId="MOCK-001",
            path=path,
            line=line_no,
            severity="critical",
            category="security",
            title="eval usage",
            evidence=text
        ))

    if MOCK_002_REGEX.search(text):
        findings.append(Finding(
            id=f"MOCK-002:{path}:{line_no}",
            ruleId="MOCK-002",
            path=path,
            line=line_no,
            severity="critical",
            category="security",
            title="hardcoded credential",
            evidence=text
        ))

    if MOCK_003_REGEX.search(text):
        findings.append(Finding(
            id=f"MOCK-003:{path}:{line_no}",
            ruleId="MOCK-003",
            path=path,
            line=line_no,
            severity="high",
            category="security",
            title="SQL string concatenation",
            evidence=text
        ))

    if "== null" in text or "!= null" in text:
        findings.append(Finding(
            id=f"MOCK-005:{path}:{line_no}",
            ruleId="MOCK-005",
            path=path,
            line=line_no,
            severity="medium",
            category="correctness",
            title="loose null comparison",
            evidence=text
        ))

    if "JSON.parse(JSON.stringify(" in text:
        findings.append(Finding(
            id=f"MOCK-006:{path}:{line_no}",
            ruleId="MOCK-006",
            path=path,
            line=line_no,
            severity="medium",
            category="performance",
            title="deep-clone via JSON",
            evidence=text
        ))

    if "console.log(" in text:
        findings.append(Finding(
            id=f"MOCK-007:{path}:{line_no}",
            ruleId="MOCK-007",
            path=path,
            line=line_no,
            severity="low",
            category="style",
            title="console.log left in",
            evidence=text
        ))

    if "TODO" in text or "FIXME" in text:
        findings.append(Finding(
            id=f"MOCK-008:{path}:{line_no}",
            ruleId="MOCK-008",
            path=path,
            line=line_no,
            severity="low",
            category="style",
            title="unresolved marker",
            evidence=text
        ))

    if MOCK_INJ_REGEX.search(text):
        findings.append(Finding(
            id=f"MOCK-INJ:{path}:{line_no}",
            ruleId="MOCK-INJ",
            path=path,
            line=line_no,
            severity="critical",
            category="security",
            title="prompt-injection content",
            evidence=text
        ))

    return findings

class MockProvider(BaseProvider):
    async def analyze_chunk(self, chunk: DiffChunk) -> list[Finding]:
        raw_findings: list[Finding] = []
        for file in chunk.files:
            for line_item in file.added_lines:
                raw_findings.extend(evaluate_line_rules(line_item))
            raw_findings.extend(scan_mock_004(file.added_lines))
        return raw_findings
