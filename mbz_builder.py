# mbz_builder.py
# Minimal Moodle backup (.mbz) builder for a single quiz + its question bank.
# Works with the structures produced by your Question Builder and Quiz Builder.

import os, io, time, zipfile, hashlib, random, string
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

# ---------------------------
# Small ID registry utilities
# ---------------------------
class Ids:
    def __init__(self):
        self.cat = 1000
        self.entry = 2000
        self.version = 3000
        self.question = 4000
        self.quiz = 5000
        self.slot = 6000

    def next(self, name: str) -> int:
        v = getattr(self, name)
        setattr(self, name, v + 1)
        return v

def _now_unix() -> int:
    return int(time.time())

def _uniq_stamp(prefix: str) -> str:
    return f"{prefix}_{_now_unix()}_{''.join(random.choices(string.ascii_lowercase+string.digits, k=6))}"

# -------------------------------------------------------
# QUESTIONS.XML  (Categories → Entries → Versions → Qs)
# Input question shape matches your app:
#   {"type": "Multiple Choice"|"True/False"|"Short Answer"|"Essay"|"Cloze",
#    "name": str, "text": str, "points": float, ...}
# -------------------------------------------------------
def build_questions_xml(category_name: str, questions: List[Dict[str, Any]]) -> bytes:
    ids = Ids()
    root = ET.Element("question_categories")
    # Category
    cat_id = ids.next("cat")
    qcat = ET.SubElement(root, "question_category", {"id": str(cat_id)})
    ET.SubElement(qcat, "name").text = category_name or "Default category"
    ET.SubElement(qcat, "idnumber").text = "$@NULL@$"
    # Context placeholders (Moodle remaps these on restore)
    ET.SubElement(qcat, "contextid").text = "1"
    ET.SubElement(qcat, "contextlevel").text = "50"
    ET.SubElement(qcat, "contextinstanceid").text = "1"

    # Entries
    entries = ET.SubElement(root, "question_bank_entries")

    # One entry per question
    for q in questions:
        entry_id = ids.next("entry")
        e = ET.SubElement(entries, "question_bank_entry", {"id": str(entry_id)})
        ET.SubElement(e, "questioncategoryid").text = str(cat_id)
        ET.SubElement(e, "idnumber").text = "$@NULL@$"

        # Versions wrapper
        versions = ET.SubElement(e, "question_versions")
        version_id = ids.next("version")
        v = ET.SubElement(versions, "question_version", {"id": str(version_id)})
        ET.SubElement(v, "questionbankentryid").text = str(entry_id)
        ET.SubElement(v, "version").text = "1"
        ET.SubElement(v, "status").text = "ready"

        # Actual <question>
        q_id = ids.next("question")
        qnode = ET.SubElement(v, "question", {"id": str(q_id)})
        qtype = _map_qtype(q.get("type"))
        ET.SubElement(qnode, "qtype").text = qtype
        ET.SubElement(qnode, "name").text = q.get("name", "Untitled")
        # questiontext + format
        qt = ET.SubElement(qnode, "questiontext")
        ET.SubElement(qt, "text").text = q.get("text", "")
        ET.SubElement(qnode, "questiontextformat").text = "1"
        # generalfeedback (optional empty)
        gf = ET.SubElement(qnode, "generalfeedback")
        ET.SubElement(gf, "text").text = ""
        ET.SubElement(qnode, "generalfeedbackformat").text = "1"
        # defaultmark + penalty
        ET.SubElement(qnode, "defaultmark").text = str(float(q.get("points", 1.0)))
        ET.SubElement(qnode, "penalty").text = "0.0000000"
        # housekeeping
        ET.SubElement(qnode, "stamp").text = _uniq_stamp("q")
        now = str(_now_unix())
        ET.SubElement(qnode, "timecreated").text = now
        ET.SubElement(qnode, "timemodified").text = now
        ET.SubElement(qnode, "createdby").text = "2"
        ET.SubElement(qnode, "modifiedby").text = "2"

        # Type-specific payload
        if qtype == "multichoice":
            _add_multichoice_payload(qnode, q)
        elif qtype == "truefalse":
            _add_truefalse_payload(qnode, q)
        elif qtype == "shortanswer":
            _add_shortanswer_payload(qnode, q)
        elif qtype == "essay":
            _add_essay_payload(qnode)
        elif qtype == "cloze":
            _add_cloze_payload(qnode, q)
        else:
            pass

    # Serialize
    return _et_to_bytes(root)

def _map_qtype(ui_type: str) -> str:
    t = (ui_type or "").strip().lower()
    return {
        "multiple choice": "multichoice",
        "true/false": "truefalse",
        "short answer": "shortanswer",
        "essay": "essay",
        "cloze": "cloze",
    }.get(t, "essay")

def _add_multichoice_payload(qnode: ET.Element, q: Dict[str, Any]) -> None:
    mc = ET.SubElement(qnode, "multichoice")
    # single vs multiple: if more than one correct box checked, set to 0
    correct_idx = set(q.get("correct", []))
    single = 1 if len(correct_idx) <= 1 else 0
    ET.SubElement(mc, "single").text = str(single)
    ET.SubElement(mc, "shuffleanswers").text = "1"
    ET.SubElement(mc, "answernumbering").text = "abc"
    for i, text in enumerate(q.get("options", []), start=1):
        ans = ET.SubElement(qnode, "answer")
        # fraction 1.0 when chosen index is correct
        fraction = "1.0000000" if i in correct_idx else "0.0000000"
        ET.SubElement(ans, "fraction").text = fraction
        at = ET.SubElement(ans, "answertext")
        ET.SubElement(at, "text").text = text or ""
        ET.SubElement(ans, "feedback").text = ""
        ET.SubElement(ans, "feedbackformat").text = "1"
    # standard feedbacks
    for tag in ("correctfeedback", "partiallycorrectfeedback", "incorrectfeedback"):
        node = ET.SubElement(mc, tag); ET.SubElement(node, "text").text = ""
        ET.SubElement(mc, f"{tag}format").text = "1"
    ET.SubElement(mc, "shownumcorrect").text = "0"
    ET.SubElement(mc, "showstandardinstruction").text = "1"

def _add_truefalse_payload(qnode: ET.Element, q: Dict[str, Any]) -> None:
    # Moodle TF usually records two <answer> nodes with fractions 1.0 and 0.0
    correct_is_true = (q.get("answer", "True").strip().lower() == "true")
    for label, frac in (("true", "1.0000000" if correct_is_true else "0.0000000"),
                        ("false", "1.0000000" if not correct_is_true else "0.0000000")):
        ans = ET.SubElement(qnode, "answer")
        ET.SubElement(ans, "fraction").text = frac
        at = ET.SubElement(ans, "answertext")
        ET.SubElement(at, "text").text = label
        ET.SubElement(ans, "feedback").text = ""
        ET.SubElement(ans, "feedbackformat").text = "1"

def _add_shortanswer_payload(qnode: ET.Element, q: Dict[str, Any]) -> None:
    sa = ET.SubElement(qnode, "shortanswer")
    ET.SubElement(sa, "usecase").text = "0"
    ans = ET.SubElement(qnode, "answer")
    ET.SubElement(ans, "fraction").text = "1.0000000"
    at = ET.SubElement(ans, "answertext")
    ET.SubElement(at, "text").text = q.get("correct_answer", "")
    ET.SubElement(ans, "feedback").text = ""
    ET.SubElement(ans, "feedbackformat").text = "1"

def _add_essay_payload(qnode: ET.Element) -> None:
    # Keep defaults minimal — Moodle provides sensible behaviour
    ET.SubElement(qnode, "responseformat").text = "editor"
    ET.SubElement(qnode, "responserequired").text = "1"

def _add_cloze_payload(qnode: ET.Element, q: Dict[str, Any]) -> None:
    # Cloze is stored in questiontext; nothing else is required here.
    pass

def _et_to_bytes(root: ET.Element) -> bytes:
    # pretty-ish print
    _indent_xml(root)
    buf = io.BytesIO()
    buf.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
    buf.write(ET.tostring(root, encoding="utf-8"))
    return buf.getvalue()

def _indent_xml(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for e in elem:
            _indent_xml(e, level+1)
            if not e.tail or not e.tail.strip():
                e.tail = i
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

# -------------------------------------------------------
# QUIZ.XML (+ question_instances with bank entry refs)
# -------------------------------------------------------
def build_quiz_xml(quiz_name: str,
                   intro_html: str,
                   question_bank_entry_ids: List[int],
                   per_slot_maxmark: float = 1.0) -> bytes:
    ids = Ids()
    quiz_id = ids.next("quiz")
    root = ET.Element("quiz", {"id": str(quiz_id)})
    ET.SubElement(root, "name").text = quiz_name or "Quiz"
    intro = ET.SubElement(root, "intro"); ET.SubElement(intro, "text").text = intro_html or ""
    ET.SubElement(root, "introformat").text = "1"
    # minimalist behaviour settings
    ET.SubElement(root, "preferredbehaviour").text = "deferredfeedback"
    ET.SubElement(root, "attempts_number").text = "0"
    ET.SubElement(root, "grademethod").text = "1"
    ET.SubElement(root, "timeopen").text = "0"
    ET.SubElement(root, "timeclose").text = "0"
    ET.SubElement(root, "timelimit").text = "0"
    # instances (slots)
    qis = ET.SubElement(root, "question_instances")
    page = 1
    for idx, entry_id in enumerate(question_bank_entry_ids, start=1):
        qi = ET.SubElement(qis, "question_instance", {"id": str(ids.next("slot"))})
        ET.SubElement(qi, "slot").text = str(idx)
        ET.SubElement(qi, "page").text = str(page)
        ET.SubElement(qi, "requireprevious").text = "0"
        ET.SubElement(qi, "maxmark").text = str(float(per_slot_maxmark))
        qref = ET.SubElement(qi, "question_reference")
        ET.SubElement(qref, "component").text = "mod_quiz"
        ET.SubElement(qref, "questionarea").text = "slot"
        ET.SubElement(qref, "questionbankentryid").text = str(entry_id)
    return _et_to_bytes(root)

# -------------------------------------------------------
# MODULE.XML (placement/visibility stub for the quiz)
# -------------------------------------------------------
def build_module_xml(quiz_name: str) -> bytes:
    root = ET.Element("module")
    ET.SubElement(root, "modulename").text = "quiz"
    ET.SubElement(root, "sectionnumber").text = "1"
    ET.SubElement(root, "visible").text = "1"
    ET.SubElement(root, "visibleoncoursepage").text = "1"
    ET.SubElement(root, "idnumber").text = "$@NULL@$"
    ET.SubElement(root, "score").text = "0"
    ET.SubElement(root, "name").text = quiz_name or "Quiz"
    return _et_to_bytes(root)

# -------------------------------------------------------
# MOODLE_BACKUP.XML  (archive header)
# -------------------------------------------------------
def build_moodle_backup_xml(include_files: bool = False) -> bytes:
    root = ET.Element("moodle_backup")
    info = ET.SubElement(root, "information")
    ET.SubElement(info, "name").text = _uniq_stamp("backup")
    ET.SubElement(info, "moodle_version").text = "2024042200"  # 4.5 series; safe default
    ET.SubElement(info, "moodle_release").text = "4.5"
    ET.SubElement(info, "backup_version").text = "2024042200"
    ET.SubElement(info, "backup_release").text = "4.5"
    ET.SubElement(info, "backup_date").text = str(_now_unix())
    ET.SubElement(info, "original_wwwroot").text = "https://example.invalid"
    ET.SubElement(info, "include_files").text = "1" if include_files else "0"
    return _et_to_bytes(root)

# -------------------------------------------------------
# High-level: build a ready-to-import .mbz in-memory
# -------------------------------------------------------
def build_quiz_mbz(category_name: str,
                   questions: List[Dict[str, Any]],
                   quiz_name: str,
                   intro_html: str = "") -> bytes:
    # 1) Build questions.xml and capture the order of entry IDs for slot references
    #    (We re-run the same allocation so IDs are stable/known.)
    #    To keep things deterministic, allocate entry IDs first:
    entry_ids = list(range(2000, 2000 + len(questions)))  # mirrors Ids().entry starting at 2000
    questions_xml = build_questions_xml(category_name, questions)

    # 2) Build quiz.xml referencing those entry IDs
    quiz_xml = build_quiz_xml(quiz_name, intro_html, entry_ids, per_slot_maxmark=1.0)

    # 3) Build module.xml and moodle_backup.xml
    module_xml = build_module_xml(quiz_name)
    backup_xml = build_moodle_backup_xml(include_files=False)

    # 4) Assemble the .mbz structure
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("moodle_backup.xml", backup_xml)
        z.writestr("questions.xml", questions_xml)
        # create a stable folder name for the activity (quiz_5000)
        z.writestr("activities/quiz_5000/quiz.xml", quiz_xml)
        z.writestr("activities/quiz_5000/module.xml", module_xml)
        # inforef.xml is optional for this minimal case; omit until you add files
    return buf.getvalue()
