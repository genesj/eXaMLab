## Written by Gene Smith-James
## Version 1.1 - MacOS compatibility

#-----------------------------
#region Imports
#-----------------------------
import os
import copy
import io
import logging
import platform
import time
import zipfile
import tkinter as tk
from tkinter import messagebox, filedialog, ttk, Text
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Tuple
# import DateEntry used in quizBuilder; Calendar is optional if you need it elsewhere
from tkcalendar import DateEntry
basedir = os.path.dirname(__file__)

#-----------------------------
#endregion Imports
#-----------------------------
#region MBZ Builder Utilities
#-----------------------------
def _now_unix() -> int:
    return int(time.time())

def _uniq_suffix(n=6) -> str:
    import secrets
    import string as _string

    alpha = _string.ascii_lowercase + _string.digits
    return ''.join(secrets.choice(alpha) for _ in range(n))

def _indent_xml(elem, level=0):
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for e in elem:
            _indent_xml(e, level + 1)
            if not e.tail or not e.tail.strip():
                e.tail = i
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def _et_to_bytes(root: ET.Element) -> bytes:
    _indent_xml(root)
    buf = io.BytesIO()
    buf.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
    buf.write(ET.tostring(root, encoding="utf-8"))
    return buf.getvalue()


def build_empty_roles_xml() -> bytes:
    root = ET.Element("roles")
    ET.SubElement(root, "role_overrides")  # can be empty
    ET.SubElement(root, "role_assignments")  # can be empty
    return _et_to_bytes(root)


def build_empty_grades_xml() -> bytes:
    root = ET.Element("grades")
    ET.SubElement(root, "grade_items")  # no <grade_item> children since no users/grades
    ET.SubElement(root, "grade_grades")  # no <grade_grade> rows either
    ET.SubElement(root, "grade_letters")  # empty is fine
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
    correct_idx = set(q.get("correct", []))
    single = 1 if len(correct_idx) <= 1 else 0
    ET.SubElement(mc, "single").text = str(single)
    ET.SubElement(mc, "shuffleanswers").text = "1"
    ET.SubElement(mc, "answernumbering").text = "abc"
    for i, text in enumerate(q.get("options", []), start=1):
        ans = ET.SubElement(qnode, "answer")
        ET.SubElement(ans, "fraction").text = "1.0000000" if i in correct_idx else "0.0000000"
        at = ET.SubElement(ans, "answertext")
        ET.SubElement(at, "text").text = text or ""
        ET.SubElement(ans, "feedback").text = ""
        ET.SubElement(ans, "feedbackformat").text = "1"
    for tag in ("correctfeedback", "partiallycorrectfeedback", "incorrectfeedback"):
        node = ET.SubElement(mc, tag)
        ET.SubElement(node, "text").text = ""
        ET.SubElement(mc, f"{tag}format").text = "1"
    ET.SubElement(mc, "shownumcorrect").text = "0"
    ET.SubElement(mc, "showstandardinstruction").text = "1"


def _add_truefalse_payload(qnode: ET.Element, q: Dict[str, Any]) -> None:
    correct_is_true = (str(q.get("answer", "True")).strip().lower() == "true")
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
    ET.SubElement(qnode, "responseformat").text = "editor"
    ET.SubElement(qnode, "responserequired").text = "1"


def _add_cloze_payload(qnode: ET.Element, q: Dict[str, Any]) -> None:
    # Cloze content is embedded in questiontext; nothing else required here.
    pass


def build_questions_xml(category_name: str, questions: List[Dict[str, Any]]) -> bytes:
    """
    Build a Moodle 4.5-style questions.xml:
    - Two categories: a 'top' (id=1000) and a 'Default for <course>' (id=1001)
    - Each question becomes one question_bank_entry under the default category
    - Plugin blocks: multichoice / truefalse / shortanswer
    - Uses $@NULL@$ where Moodle commonly uses placeholders
    """
    now = str(_now_unix())
    root = ET.Element("question_categories")

    # ---- Category 1: 'top' (empty, parent=0) ----
    cat_top = ET.SubElement(root, "question_category", {"id": "1000"})
    ET.SubElement(cat_top, "name").text = "top"
    # Context: course-level (50). Moodle remaps on restore; numeric values are fine.
    ET.SubElement(cat_top, "contextid").text = "1"
    ET.SubElement(cat_top, "contextlevel").text = "50"
    ET.SubElement(cat_top, "contextinstanceid").text = "1"
    ET.SubElement(cat_top, "info").text = ""
    ET.SubElement(cat_top, "infoformat").text = "0"
    ET.SubElement(cat_top, "stamp").text = f"generated+{now}+top"
    ET.SubElement(cat_top, "parent").text = "0"
    ET.SubElement(cat_top, "sortorder").text = "0"
    ET.SubElement(cat_top, "idnumber").text = "$@NULL@$"
    ET.SubElement(cat_top, "question_bank_entries")

    # ---- Category 2: 'Default for <course>' (holds entries) ----
    display_name = category_name or "Default for Generated Course"
    cat_def = ET.SubElement(root, "question_category", {"id": "1001"})
    ET.SubElement(cat_def, "name").text = display_name
    ET.SubElement(cat_def, "contextid").text = "1"
    ET.SubElement(cat_def, "contextlevel").text = "50"
    ET.SubElement(cat_def, "contextinstanceid").text = "1"
    ET.SubElement(cat_def, "info").text = f"The default category for questions shared in context '{display_name}'."
    ET.SubElement(cat_def, "infoformat").text = "0"
    ET.SubElement(cat_def, "stamp").text = f"generated+{now}+default"
    ET.SubElement(cat_def, "parent").text = "1000"
    ET.SubElement(cat_def, "sortorder").text = "999"
    ET.SubElement(cat_def, "idnumber").text = "$@NULL@$"

    entries = ET.SubElement(cat_def, "question_bank_entries")

    def add_multichoice_plugin(qnode: ET.Element, q: Dict[str, Any]) -> None:
        plugin = ET.SubElement(qnode, "plugin_qtype_multichoice_question")
        answers = ET.SubElement(plugin, "answers")
        correct = set(q.get("correct", []))
        opts = q.get("options", []) or []
        for idx, opt in enumerate(opts, start=1):
            ans = ET.SubElement(answers, "answer", {"id": str(90000000 + idx)})
            ET.SubElement(ans, "answertext").text = opt or ""
            ET.SubElement(ans, "answerformat").text = "1"
            ET.SubElement(ans, "fraction").text = "1.0000000" if idx in correct else "0.0000000"
            ET.SubElement(ans, "feedback").text = ""
            ET.SubElement(ans, "feedbackformat").text = "1"
        mc = ET.SubElement(plugin, "multichoice", {"id": str(19000000)})
        ET.SubElement(mc, "layout").text = "0"
        ET.SubElement(mc, "single").text = "1" if len(correct) <= 1 else "0"
        ET.SubElement(mc, "shuffleanswers").text = "0"
        ET.SubElement(mc, "correctfeedback").text = "Your answer is correct."
        ET.SubElement(mc, "correctfeedbackformat").text = "1"
        ET.SubElement(mc, "partiallycorrectfeedback").text = "Your answer is partially correct."
        ET.SubElement(mc, "partiallycorrectfeedbackformat").text = "1"
        ET.SubElement(mc, "incorrectfeedback").text = "Your answer is incorrect."
        ET.SubElement(mc, "incorrectfeedbackformat").text = "1"
        ET.SubElement(mc, "answernumbering").text = "abc"
        ET.SubElement(mc, "shownumcorrect").text = "0"
        ET.SubElement(mc, "showstandardinstruction").text = "0"

    def add_truefalse_plugin(qnode: ET.Element, q: Dict[str, Any]) -> None:
        plugin = ET.SubElement(qnode, "plugin_qtype_truefalse_question")
        answers = ET.SubElement(plugin, "answers")
        true_id = 92214143
        false_id = 92214144
        for label, ans_id, frac in (("True", true_id, "1.0000000" if str(q.get("answer", "True")).lower() == "true" else "0.0000000"),
                                    ("False", false_id, "1.0000000" if str(q.get("answer", "True")).lower() == "false" else "0.0000000")):
            ans = ET.SubElement(answers, "answer", {"id": str(ans_id)})
            ET.SubElement(ans, "answertext").text = label
            ET.SubElement(ans, "answerformat").text = "0"
            ET.SubElement(ans, "fraction").text = frac
            ET.SubElement(ans, "feedback").text = ""
            ET.SubElement(ans, "feedbackformat").text = "1"
        tf = ET.SubElement(plugin, "truefalse", {"id": "2777761"})
        ET.SubElement(tf, "trueanswer").text = str(true_id)
        ET.SubElement(tf, "falseanswer").text = str(false_id)
        ET.SubElement(tf, "showstandardinstruction").text = "0"

    def add_shortanswer_plugin(qnode: ET.Element, q: Dict[str, Any]) -> None:
        plugin = ET.SubElement(qnode, "plugin_qtype_shortanswer_question")
        answers = ET.SubElement(plugin, "answers")
        ans = ET.SubElement(answers, "answer", {"id": "92214138"})
        ET.SubElement(ans, "answertext").text = q.get("correct_answer", "")
        ET.SubElement(ans, "answerformat").text = "0"
        ET.SubElement(ans, "fraction").text = "1.0000000"
        ET.SubElement(ans, "feedback").text = ""
        ET.SubElement(ans, "feedbackformat").text = "1"
        sa = ET.SubElement(plugin, "shortanswer", {"id": "2182262"})
        ET.SubElement(sa, "usecase").text = "0"

    def add_common_plugin_stubs(qnode: ET.Element) -> None:
        ET.SubElement(qnode, "plugin_qbank_comment_question").append(ET.Element("comments"))
        ET.SubElement(qnode, "plugin_qbank_customfields_question").append(ET.Element("customfields"))
        ET.SubElement(qnode, "plugin_outcomesupport_qtype_question").append(ET.Element("outcome_areas"))
        ET.SubElement(qnode, "question_hints")

    question_ids: List[int] = []
    entry_ids_record: List[int] = []

    for idx, q in enumerate(questions):
        entry_id = 12300000 + idx
        entry_ids_record.append(entry_id)
        e = ET.SubElement(entries, "question_bank_entry", {"id": str(entry_id)})
        ET.SubElement(e, "questioncategoryid").text = "1001"
        ET.SubElement(e, "idnumber").text = "$@NULL@$"
        ET.SubElement(e, "ownerid").text = "$@NULL@$"

        qversions = ET.SubElement(e, "question_versions")
        qv = ET.SubElement(qversions, "question_version", {"id": str(12550000 + idx)})
        ET.SubElement(qv, "version").text = "1"
        ET.SubElement(qv, "status").text = "ready"

        question_id = 35640000 + idx
        question_ids.append(question_id)
        qnode = ET.SubElement(qv, "question", {"id": str(question_id)})

        qtype_in = (q.get("type") or "multichoice").strip().lower()
        if qtype_in in ("multiple choice", "multichoice"):
            mqtype = "multichoice"
        elif qtype_in in ("true/false", "truefalse", "tf"):
            mqtype = "truefalse"
        elif qtype_in in ("short answer", "shortanswer"):
            mqtype = "shortanswer"
        else:
            mqtype = "shortanswer"

        now = str(_now_unix())
        ET.SubElement(qnode, "parent").text = "0"
        ET.SubElement(qnode, "name").text = q.get("name", "Untitled")
        ET.SubElement(qnode, "questiontext").text = q.get("text", "")
        ET.SubElement(qnode, "questiontextformat").text = "1"
        ET.SubElement(qnode, "generalfeedback").text = ""
        ET.SubElement(qnode, "generalfeedbackformat").text = "1"
        ET.SubElement(qnode, "defaultmark").text = f"{float(q.get('points', 1.0)):.7f}"
        ET.SubElement(qnode, "penalty").text = "1.0000000" if mqtype == "truefalse" else "0.3333333"
        ET.SubElement(qnode, "qtype").text = mqtype
        ET.SubElement(qnode, "length").text = "1"
        ET.SubElement(qnode, "stamp").text = f"generated+{now}+{mqtype}+{idx}"
        ET.SubElement(qnode, "timecreated").text = now
        ET.SubElement(qnode, "timemodified").text = now
        ET.SubElement(qnode, "createdby").text = "$@NULL@$"
        ET.SubElement(qnode, "modifiedby").text = "$@NULL@$"

        if mqtype == "multichoice":
            plugin = ET.SubElement(qnode, "plugin_qtype_multichoice_question")
            answers = ET.SubElement(plugin, "answers")
            correct = set(q.get("correct", []))
            opts = q.get("options", []) or []
            for i, opt in enumerate(opts, start=1):
                ans = ET.SubElement(answers, "answer", {"id": str(90000000 + i)})
                ET.SubElement(ans, "answertext").text = opt or ""
                ET.SubElement(ans, "answerformat").text = "1"
                ET.SubElement(ans, "fraction").text = "1.0000000" if i in correct else "0.0000000"
                ET.SubElement(ans, "feedback").text = ""
                ET.SubElement(ans, "feedbackformat").text = "1"
            mc = ET.SubElement(plugin, "multichoice", {"id": str(19000000 + idx)})
            ET.SubElement(mc, "layout").text = "0"
            ET.SubElement(mc, "single").text = "1" if len(correct) <= 1 else "0"
            ET.SubElement(mc, "shuffleanswers").text = "0"
            ET.SubElement(mc, "correctfeedback").text = "Your answer is correct."
            ET.SubElement(mc, "correctfeedbackformat").text = "1"
            ET.SubElement(mc, "partiallycorrectfeedback").text = "Your answer is partially correct."
            ET.SubElement(mc, "partiallycorrectfeedbackformat").text = "1"
            ET.SubElement(mc, "incorrectfeedback").text = "Your answer is incorrect."
            ET.SubElement(mc, "incorrectfeedbackformat").text = "1"
            ET.SubElement(mc, "answernumbering").text = "abc"
            ET.SubElement(mc, "shownumcorrect").text = "0"
            ET.SubElement(mc, "showstandardinstruction").text = "0"
        elif mqtype == "truefalse":
            plugin = ET.SubElement(qnode, "plugin_qtype_truefalse_question")
            answers = ET.SubElement(plugin, "answers")
            true_id = 92214143
            false_id = 92214144
            want_true = str(q.get("answer", "True")).strip().lower() == "true"
            for label, ans_id, frac in (
                ("True", true_id, "1.0000000" if want_true else "0.0000000"),
                ("False", false_id, "1.0000000" if not want_true else "0.0000000"),
            ):
                ans = ET.SubElement(answers, "answer", {"id": str(ans_id)})
                ET.SubElement(ans, "answertext").text = label
                ET.SubElement(ans, "answerformat").text = "0"
                ET.SubElement(ans, "fraction").text = frac
                ET.SubElement(ans, "feedback").text = ""
                ET.SubElement(ans, "feedbackformat").text = "1"
            tf = ET.SubElement(plugin, "truefalse", {"id": str(2777761 + idx)})
            ET.SubElement(tf, "trueanswer").text = str(true_id)
            ET.SubElement(tf, "falseanswer").text = str(false_id)
            ET.SubElement(tf, "showstandardinstruction").text = "0"
        else:
            plugin = ET.SubElement(qnode, "plugin_qtype_shortanswer_question")
            answers = ET.SubElement(plugin, "answers")
            ans = ET.SubElement(answers, "answer", {"id": str(92214138 + idx)})
            ET.SubElement(ans, "answertext").text = q.get("correct_answer", "")
            ET.SubElement(ans, "answerformat").text = "0"
            ET.SubElement(ans, "fraction").text = "1.0000000"
            ET.SubElement(ans, "feedback").text = ""
            ET.SubElement(ans, "feedbackformat").text = "1"
            sa = ET.SubElement(plugin, "shortanswer", {"id": str(2182262 + idx)})
            ET.SubElement(sa, "usecase").text = "0"

        ET.SubElement(qnode, "plugin_qbank_comment_question").append(ET.Element("comments"))
        ET.SubElement(qnode, "plugin_qbank_customfields_question").append(ET.Element("customfields"))
        ET.SubElement(qnode, "plugin_outcomesupport_qtype_question").append(ET.Element("outcome_areas"))
        ET.SubElement(qnode, "question_hints")

    build_questions_xml._last_question_ids = question_ids
    build_questions_xml._last_entry_ids = entry_ids_record
    return _et_to_bytes(root)


def _derive_quiz_identifiers(moduleid: int) -> Tuple[int, int, int, int]:
    """Return identifiers for the quiz activity derived from ``moduleid``.

    The tuple contains ``(activity_id, quiz_id, question_instance_base,
    slot_base)`` ensuring that every generated quiz, as well as the nested
    question instance and slot records, receive deterministic yet unique
    identifiers when multiple quizzes are exported in a single archive.
    """

    base = moduleid if moduleid > 0 else 1
    activity_id = base * 10
    quiz_id = activity_id + 1
    question_instance_base = base * 1000
    slot_base = question_instance_base + 500
    return activity_id, quiz_id, question_instance_base, slot_base


def build_quiz_activity_xml(
    moduleid: int,
    quiz_name: str,
    intro_html: str = "",
    entry_ids: list[int] | None = None,
    question_infos: List[Dict[str, Any]] | None = None,
    per_slot_maxmark: float = 1.0,
    identifiers: Tuple[int, int, int, int] | None = None,
) -> bytes:
    # Derive stable identifiers from the supplied moduleid so that each
    # exported quiz receives unique values instead of the previous fixed
    # placeholder. Multiplying by 10 keeps the identifiers in the same
    # numeric range while avoiding collisions when multiple module IDs are
    # sequential (e.g., moduleid=100, 101, ...).
    activity_id, quiz_id, qi_base, slot_base = identifiers or _derive_quiz_identifiers(moduleid)

    root = ET.Element(
        "activity",
        {
            "id": str(activity_id),
            "moduleid": str(moduleid),
            "modulename": "quiz",
            "contextid": "1",
        },
    )

    quiz = ET.SubElement(root, "quiz", {"id": str(quiz_id)})
    ET.SubElement(quiz, "name").text = quiz_name or "Quiz"
    ET.SubElement(quiz, "intro").text = intro_html or ""
    ET.SubElement(quiz, "introformat").text = "1"

    ET.SubElement(quiz, "timeopen").text = "0"
    ET.SubElement(quiz, "timeclose").text = "0"
    ET.SubElement(quiz, "timelimit").text = "0"
    ET.SubElement(quiz, "overduehandling").text = "autosubmit"
    ET.SubElement(quiz, "graceperiod").text = "0"
    ET.SubElement(quiz, "preferredbehaviour").text = "deferredfeedback"
    ET.SubElement(quiz, "canredoquestions").text = "0"

    ET.SubElement(quiz, "attempts_number").text = "1"
    ET.SubElement(quiz, "attemptonlast").text = "0"
    ET.SubElement(quiz, "grademethod").text = "1"
    ET.SubElement(quiz, "decimalpoints").text = "2"
    ET.SubElement(quiz, "questiondecimalpoints").text = "-1"

    for k, v in {
        "reviewattempt": "65536",
        "reviewcorrectness": "4096",
        "reviewmarks": "4096",
        "reviewspecificfeedback": "4096",
        "reviewgeneralfeedback": "4096",
        "reviewrightanswer": "4096",
        "reviewoverallfeedback": "4096",
    }.items():
        ET.SubElement(quiz, k).text = v

    ET.SubElement(quiz, "questionsperpage").text = "5"
    ET.SubElement(quiz, "navmethod").text = "free"
    ET.SubElement(quiz, "shuffleanswers").text = "0"
    question_instances = ET.SubElement(quiz, "question_instances")

    slots_node = ET.SubElement(quiz, "slots")

    sections = ET.SubElement(quiz, "sections")
    if entry_ids or question_infos:
        sec = ET.SubElement(sections, "section", {"id": str(activity_id)})
        ET.SubElement(sec, "firstslot").text = "1"
        ET.SubElement(sec, "shufflequestions").text = "0"
        ET.SubElement(sec, "slotcount").text = str(len(question_infos or entry_ids or []))

    total = 0.0

    if question_infos:
        for slot_index, info in enumerate(question_infos, start=1):
            question_id = int(info.get("question_id", 0))
            maxmark = float(info.get("maxmark", per_slot_maxmark) or per_slot_maxmark)
            qi_id = qi_base + slot_index
            qi = ET.SubElement(question_instances, "question_instance", {"id": str(qi_id)})
            ET.SubElement(qi, "slot").text = str(slot_index)
            ET.SubElement(qi, "questionid").text = str(question_id)
            ET.SubElement(qi, "maxmark").text = f"{maxmark:.5f}"

            slot_id = slot_base + slot_index
            slot = ET.SubElement(slots_node, "slot", {"id": str(slot_id)})
            ET.SubElement(slot, "slotnumber").text = str(slot_index)
            ET.SubElement(slot, "quizpage").text = "1"
            ET.SubElement(slot, "requireprevious").text = "0"
            ET.SubElement(slot, "questionid").text = str(question_id)
            ET.SubElement(slot, "questioninstanceid").text = str(qi_id)
            ET.SubElement(slot, "maxmark").text = f"{maxmark:.5f}"
            ET.SubElement(slot, "minmark").text = "0.00000"

            total += maxmark
    elif entry_ids:
        for slot_index, entry_id in enumerate(entry_ids, start=1):
            maxmark = per_slot_maxmark
            qi_id = qi_base + slot_index
            qi = ET.SubElement(question_instances, "question_instance", {"id": str(qi_id)})
            ET.SubElement(qi, "slot").text = str(slot_index)
            ET.SubElement(qi, "questionid").text = str(entry_id)
            ET.SubElement(qi, "maxmark").text = f"{maxmark:.5f}"

            slot_id = slot_base + slot_index
            slot = ET.SubElement(slots_node, "slot", {"id": str(slot_id)})
            ET.SubElement(slot, "slotnumber").text = str(slot_index)
            ET.SubElement(slot, "quizpage").text = "1"
            ET.SubElement(slot, "requireprevious").text = "0"
            ET.SubElement(slot, "questionid").text = str(entry_id)
            ET.SubElement(slot, "questioninstanceid").text = str(qi_id)
            ET.SubElement(slot, "maxmark").text = f"{maxmark:.5f}"
            ET.SubElement(slot, "minmark").text = "0.00000"

            total += maxmark
    else:
        quiz.remove(slots_node)
        quiz.remove(question_instances)

    ET.SubElement(quiz, "sumgrades").text = f"{total:.5f}"
    ET.SubElement(quiz, "grade").text = f"{total:.5f}" if total else "0.00000"

    now = str(_now_unix())
    ET.SubElement(quiz, "timecreated").text = now
    ET.SubElement(quiz, "timemodified").text = now
    ET.SubElement(quiz, "password").text = ""
    ET.SubElement(quiz, "subnet").text = ""
    ET.SubElement(quiz, "browsersecurity").text = "-"
    ET.SubElement(quiz, "delay1").text = "0"
    ET.SubElement(quiz, "delay2").text = "0"
    ET.SubElement(quiz, "showuserpicture").text = "0"
    ET.SubElement(quiz, "showblocks").text = "0"
    ET.SubElement(quiz, "completionattemptsexhausted").text = "0"
    ET.SubElement(quiz, "completionminattempts").text = "0"
    ET.SubElement(quiz, "allowofflineattempts").text = "0"

    ET.SubElement(quiz, "subplugin_quizaccess_seb_quiz")
    ET.SubElement(quiz, "quiz_grade_items")
    ET.SubElement(quiz, "feedbacks")
    ET.SubElement(quiz, "overrides")
    ET.SubElement(quiz, "grades")
    ET.SubElement(quiz, "attempts")

    return _et_to_bytes(root)


def build_module_xml(
    moduleid: int,
    sectionnumber: int = 1,
    visible: int = 1,
    visibleoncoursepage: int = 1,
    modname: str = "Quiz",
    instanceid: int | None = None,
) -> bytes:
    root = ET.Element("module", {"id": str(moduleid), "version": "2024100700"})
    ET.SubElement(root, "modulename").text = "quiz"
    ET.SubElement(root, "name").text = modname
    ET.SubElement(root, "sectionid").text = "$@NULL@$"
    ET.SubElement(root, "sectionnumber").text = str(sectionnumber)

    if instanceid is not None:
        ET.SubElement(root, "instance").text = str(instanceid)

    ET.SubElement(root, "idnumber").text = ""
    ET.SubElement(root, "added").text = str(_now_unix())
    ET.SubElement(root, "score").text = "0"
    ET.SubElement(root, "indent").text = "0"
    ET.SubElement(root, "visible").text = str(visible)
    ET.SubElement(root, "visibleoncoursepage").text = str(visibleoncoursepage)
    ET.SubElement(root, "visibleold").text = str(visible)
    ET.SubElement(root, "groupmode").text = "0"
    ET.SubElement(root, "groupingid").text = "0"
    ET.SubElement(root, "completion").text = "0"
    ET.SubElement(root, "completiongradeitemnumber").text = "$@NULL@$"
    ET.SubElement(root, "completionpassgrade").text = "0"
    ET.SubElement(root, "completionview").text = "0"
    ET.SubElement(root, "completionexpected").text = "0"
    ET.SubElement(root, "availability").text = "$@NULL@$"
    ET.SubElement(root, "showdescription").text = "0"
    ET.SubElement(root, "downloadcontent").text = "1"
    ET.SubElement(root, "lang").text = ""
    ET.SubElement(root, "plugin_outcomesupport_mod_module")
    ET.SubElement(root, "tags")
    return _et_to_bytes(root)


def build_moodle_backup_xml(
    modules: List[Dict[str, Any]],
    original_wwwroot: str = "https://example.invalid",
) -> bytes:
    if not modules:
        raise ValueError("At least one module is required to generate a Moodle backup manifest.")
    root = ET.Element("moodle_backup")
    info = ET.SubElement(root, "information")

    stamp = time.strftime("%Y%m%d-%H%M", time.localtime())
    archive_name = f"backup-moodle2-activities-{len(modules)}-{stamp}.mbz"
    ET.SubElement(info, "name").text = archive_name
    ET.SubElement(info, "moodle_version").text = "2024100705"
    ET.SubElement(info, "moodle_release").text = "4.5.5 (Build: 20250609)"
    ET.SubElement(info, "backup_version").text = "2024100700"
    ET.SubElement(info, "backup_release").text = "4.5"
    ET.SubElement(info, "backup_date").text = str(_now_unix())
    ET.SubElement(info, "mnet_remoteusers").text = "0"
    ET.SubElement(info, "include_files").text = "0"
    ET.SubElement(info, "include_file_references_to_external_content").text = "0"
    ET.SubElement(info, "original_wwwroot").text = original_wwwroot
    ET.SubElement(info, "original_site_identifier_hash").text = "generated"
    ET.SubElement(info, "original_course_id").text = "1"
    ET.SubElement(info, "original_course_format").text = "topics"
    ET.SubElement(info, "original_course_fullname").text = "Generated by ExamLab"
    ET.SubElement(info, "original_course_shortname").text = "EXAMLAB"
    ET.SubElement(info, "original_course_startdate").text = "0"
    ET.SubElement(info, "original_course_enddate").text = "0"
    ET.SubElement(info, "original_course_contextid").text = "1"
    ET.SubElement(info, "original_system_contextid").text = "1"

    details = ET.SubElement(info, "details")
    for _ in modules:
        detail = ET.SubElement(details, "detail", {"backup_id": f"id_{_uniq_suffix()}"})
        ET.SubElement(detail, "type").text = "activity"
        ET.SubElement(detail, "format").text = "moodle2"
        ET.SubElement(detail, "interactive").text = "1"
        ET.SubElement(detail, "mode").text = "10"
        ET.SubElement(detail, "execution").text = "1"
        ET.SubElement(detail, "executiontime").text = "0"

    contents = ET.SubElement(info, "contents")
    activities = ET.SubElement(contents, "activities")
    for module in modules:
        module_id = int(module.get("moduleid", 0))
        module_title = module.get("title", "Quiz") or "Quiz"
        act = ET.SubElement(activities, "activity")
        ET.SubElement(act, "moduleid").text = str(module_id)
        ET.SubElement(act, "sectionid").text = "$@NULL@$"
        ET.SubElement(act, "modulename").text = "quiz"
        ET.SubElement(act, "title").text = module_title
        ET.SubElement(act, "directory").text = f"activities/quiz_{module_id}"
        ET.SubElement(act, "insubsection").text = ""

    settings = ET.SubElement(info, "settings")

    def add_root_setting(name: str, value: str):
        s = ET.SubElement(settings, "setting")
        ET.SubElement(s, "level").text = "root"
        ET.SubElement(s, "name").text = name
        ET.SubElement(s, "value").text = value

    def add_activity_setting(activitykey: str, name: str, value: str):
        s = ET.SubElement(settings, "setting")
        ET.SubElement(s, "level").text = "activity"
        ET.SubElement(s, "activity").text = activitykey
        ET.SubElement(s, "name").text = name
        ET.SubElement(s, "value").text = value

    def add_setting(name: str, value: str):
        s = ET.SubElement(settings, "setting")
        ET.SubElement(s, "level").text = "root"
        ET.SubElement(s, "name").text = name
        ET.SubElement(s, "value").text = value

    add_root_setting("filename", archive_name)
    add_root_setting("users", "0")
    add_root_setting("anonymize", "0")
    add_root_setting("role_assignments", "0")
    add_root_setting("activities", str(len(modules)))
    add_root_setting("blocks", "0")
    add_root_setting("filters", "0")
    add_root_setting("comments", "0")
    add_root_setting("badges", "0")
    add_root_setting("calendarevents", "0")
    add_root_setting("userscompletion", "0")
    add_root_setting("logs", "0")
    add_root_setting("grade_histories", "0")
    add_root_setting("files", "0")
    add_root_setting("legacyfiles", "0")
    add_root_setting("questionbank", "1")
    add_root_setting("groups", "0")
    add_root_setting("competencies", "0")
    add_root_setting("customfield", "0")
    add_root_setting("contentbankcontent", "0")
    add_root_setting("xapistate", "0")

    for module in modules:
        module_id = int(module.get("moduleid", 0))
        activitykey = f"quiz_{module_id}"
        add_activity_setting(activitykey, f"{activitykey}_included", "1")
        add_activity_setting(activitykey, f"{activitykey}_userinfo", "0")

    return _et_to_bytes(root)


def build_quizzes_mbz(
    quizzes: List[Dict[str, Any]],
    moduleid_start: int = 5000,
) -> bytes:
    if not quizzes:
        raise ValueError("At least one quiz is required to build an MBZ archive.")

    normalized: List[Dict[str, Any]] = []
    all_questions: List[Dict[str, Any]] = []
    quiz_ranges: List[Tuple[int, int]] = []

    for idx, quiz in enumerate(quizzes):
        questions = list(quiz.get("questions", []) or [])
        # if not questions:
        #     raise ValueError("Each quiz must include at least one question before export.")

        start_idx = len(all_questions)
        all_questions.extend(questions)
        quiz_ranges.append((start_idx, len(all_questions)))

        normalized.append(
            {
                "moduleid": int(quiz.get("moduleid", moduleid_start + idx)),
                "quiz_name": (quiz.get("quiz_name") or f"Quiz {idx + 1}").strip(),
                "intro_html": quiz.get("intro_html", ""),
                "category_name": quiz.get("category_name", ""),
                "questions": questions,
            }
        )

    combined_category = normalized[0].get("category_name") or "Default category"
    questions_xml = build_questions_xml(combined_category, all_questions)
    question_ids = getattr(build_questions_xml, "_last_question_ids", [])
    entry_ids = getattr(build_questions_xml, "_last_entry_ids", [])

    if len(question_ids) != len(all_questions) or len(entry_ids) != len(all_questions):
        raise ValueError("Failed to map questions to Moodle identifiers during export.")

    quiz_question_infos: List[List[Dict[str, Any]]] = []
    for idx, (start, end) in enumerate(quiz_ranges):
        qinfos: List[Dict[str, Any]] = []
        for offset, pos in enumerate(range(start, end)):
            question_payload = normalized[idx]["questions"][offset]
            points = question_payload.get("points", 1.0)
            try:
                maxmark = float(points)
            except (TypeError, ValueError):
                maxmark = 1.0
            qinfos.append(
                {
                    "question_id": question_ids[pos],
                    "entry_id": entry_ids[pos],
                    "maxmark": maxmark,
                }
            )
        quiz_question_infos.append(qinfos)

    modules_meta = [
        {
            "moduleid": quiz_info["moduleid"],
            "title": quiz_info["quiz_name"] or "Quiz",
        }
        for quiz_info in normalized
    ]

    backup_xml = build_moodle_backup_xml(modules_meta)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("moodle_backup.xml", backup_xml)
        z.writestr("questions.xml", questions_xml)

        for idx, quiz_info in enumerate(normalized):
            moduleid = quiz_info["moduleid"]
            actdir = f"activities/quiz_{moduleid}/"

            identifiers = _derive_quiz_identifiers(moduleid)
            module_xml = build_module_xml(
                moduleid,
                modname=quiz_info["quiz_name"] or "Quiz",
                instanceid=identifiers[1],
            )
            quiz_xml = build_quiz_activity_xml(
                moduleid,
                quiz_info["quiz_name"],
                quiz_info["intro_html"],
                question_infos=quiz_question_infos[idx],
                identifiers=identifiers,
            )

            z.writestr(actdir + "module.xml", module_xml)
            z.writestr(actdir + "quiz.xml", quiz_xml)
            z.writestr(actdir + "roles.xml", build_empty_roles_xml())
            z.writestr(actdir + "grades.xml", build_empty_grades_xml())

        z.writestr("roles.xml", "<roles></roles>")
        z.writestr("users.xml", "<users></users>")
        z.writestr("outcomes.xml", "<outcomes></outcomes>")
        z.writestr("groups.xml", "<groups></groups>")
        z.writestr("scales.xml", "<scales></scales>")
        z.writestr("files.xml", "<files></files>")
        z.writestr("completion.xml", "<completion></completion>")
        z.writestr("badges.xml", "<badges></badges>")

    return buf.getvalue()
def build_quiz_mbz(
    category_name: str,
    questions: List[Dict[str, Any]],
    quiz_name: str,
    intro_html: str = "",
    moduleid: int = 5000,
) -> bytes:
    quiz_payload = {
        "category_name": category_name,
        "questions": questions,
        "quiz_name": quiz_name,
        "intro_html": intro_html,
        "moduleid": moduleid,
    }
    return build_quizzes_mbz([quiz_payload], moduleid_start=moduleid)
#-----------------------------
#endregion MBZ Builder Utilities
#-----------------------------
#region Platform-Specific Code
#-----------------------------
# windows: set taskbar icon
if platform.system() == "Windows":
    try:
        from ctypes import windll  # Only exists on Windows
        myappid = 'xmlab'  # Arbitrary
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except ImportError:
        pass
if platform.system() == "Windows":
    log_dir = os.path.join(os.getenv("APPDATA"), "eXaMLab", "logs")
else:  # macOS & Linux
    log_dir = os.path.expanduser("~/Library/Logs/eXaMLab")
#-----------------------------
#endregion Platform-Specific Code
#-----------------------------
#region Logging Configuration
#-----------------------------
os.makedirs(log_dir, exist_ok=True)
error_log_path = os.path.join(log_dir, "error_log.txt")
debug_log_path = os.path.join(log_dir, "debug_log.txt")
logging.basicConfig(filename=error_log_path, level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")
debug_logger = logging.getLogger('debug_logger')
debug_logger.setLevel(logging.DEBUG)
debug_handler = logging.FileHandler(debug_log_path)
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
debug_handler.setFormatter(debug_formatter)
debug_logger.addHandler(debug_handler)
debug_logger.debug("Application started successfully on " + platform.system())
#-----------------------------
#endregion Logging Configuration
#-----------------------------
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.fade_in_id = None
        widget.bind("<Enter>", self.schedule_tooltip)
        widget.bind("<Leave>", self.hide_tooltip)
        debug_logger.debug(f"New tooltip {widget} with text: {text}")
    def schedule_tooltip(self, event):
        self.fade_in_id = self.widget.after(500, self.show_tooltip)
    def show_tooltip(self):
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.wm_attributes("-alpha", 0.0)
        label = tk.Label(tw, text=self.text, justify='left', background='white', relief='solid', borderwidth=1, font=("tahoma", "10", "normal"))
        label.pack(ipadx=1)
        debug_logger.debug(f"Displayed tooltip {self.widget}")
        self.fade_in(tw, 0.0)
    def fade_in(self, window, alpha):
        alpha += 0.1
        if alpha <= 1.0:
            window.wm_attributes("-alpha", alpha)
            window.after(12, self.fade_in, window, alpha)
    def hide_tooltip(self, event):
        if self.fade_in_id:
            self.widget.after_cancel(self.fade_in_id)
            self.fade_in_id = None
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
            debug_logger.debug(f"Hidden tooltip {self.widget}")
class mainWindow:
    def __init__(self, root):
        try:
            self.root = root
            self.root.title("eXaMLab - Moodle XML Utility")
            self.root.resizable(True, True)
            self.root.minsize(750, 630)
            if platform.system() == "Windows":
                self.root.iconbitmap(os.path.join(basedir, "icon.ico"))
            else:
                pass
            
            # Top bar for info/buttons
            self.topbar = tk.Frame(self.root)
            self.topbar.pack(side=tk.TOP, fill='x')
            self.topbar_label = tk.Label(self.topbar, text="eXaMLab", font=("Arial", 14, "bold"))
            self.topbar_label.pack(side=tk.LEFT, padx=10, pady=6)
            # Create notebook for tabs
            self.notebook = ttk.Notebook(self.root)
            self.notebook.pack(fill='both', expand=True)
            # Create question builder tab
            question_tab = ttk.Frame(self.notebook)
            self.quiz_builder = questionBuilder(question_tab)
            self.quiz_builder.main_window_ref = self
            self.notebook.add(question_tab, text="Question Builder")
            # Create quiz tab (blank)
            quiz_tab = ttk.Frame(self.notebook)
            self.quiz_tab = quizBuilder(quiz_tab)
            self.quiz_tab.main_window_ref = self
            self.notebook.add(quiz_tab, text="Quiz Builder")
            # # Create assignment tab (blank)
            # assignment_tab = ttk.Frame(self.notebook)
            # self.assignment_tab = assignmentBuilder(assignment_tab)
            # self.notebook.add(assignment_tab, text="Assignment Builder")
            # # Create forum tab (blank)
            # forum_tab = ttk.Frame(self.notebook)
            # self.forum_tab = forumBuilder(forum_tab)
            # self.notebook.add(forum_tab, text="Forum Builder")
            debug_logger.debug("User interface setup complete")
        except Exception as e:
            logging.error("Error initializing the application", exc_info=True)
            debug_logger.debug("Brutal error. Cannot initialize application.")
class questionBuilder:
    def __init__(self, parent):
        try:
            self.root = parent  # Use the passed frame, not the root window
            self.questions = []
            self.undo_stack = []
            self.edit_mode = False
            self.edit_index = None
            self.mcq_option_entries = []
            self.main_window_ref = None

            # --- Category Frame (Top) ---
            category_frame = ttk.Frame(self.root, padding=(10, 10, 10, 0))
            category_frame.pack(fill=tk.X)
            self.label_category = ttk.Label(category_frame, text="Category Name:", anchor='e')
            self.label_category.pack(side=tk.LEFT, padx=(0, 10))
            self.entry_category = ttk.Entry(category_frame)
            self.entry_category.pack(side=tk.LEFT, fill=tk.X, expand=True)
            Tooltip(self.entry_category, "Enter the name of this question bank. This will be used as the category these questions belong to inside of Moodle. You can only have one category per XML file.")

            self.main_frame = ttk.Frame(self.root, padding="10")
            self.main_frame.pack(fill=tk.BOTH, expand=True)

            # Configure grid layout
            self.main_frame.columnconfigure(0, weight=1, minsize=250)
            self.main_frame.columnconfigure(1, weight=3)
            self.main_frame.rowconfigure(0, weight=1)

            # Left side: Question List
            question_list_frame = ttk.Frame(self.main_frame)
            question_list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
            question_list_frame.grid_propagate(False)
            question_list_frame.columnconfigure(0, weight=1)
            question_list_frame.rowconfigure(1, weight=1)

            ttk.Label(question_list_frame, text="Questions", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))

            self.listbox_questions = tk.Listbox(question_list_frame, selectmode=tk.EXTENDED, exportselection=False)
            self.listbox_questions.grid(row=1, column=0, columnspan=2, sticky="nsew")
            self.listbox_questions.bind("<<ListboxSelect>>", self.on_question_select)
            self.listbox_questions.bind("<Double-1>", lambda event: self.edit_question())

            # Add a scrollbar to the listbox
            scrollbar = ttk.Scrollbar(question_list_frame, orient=tk.VERTICAL, command=self.listbox_questions.yview)
            scrollbar.grid(row=1, column=1, sticky="ns")
            self.listbox_questions.config(yscrollcommand=scrollbar.set)

            # --- Buttons below listbox ---
            list_button_frame = ttk.Frame(question_list_frame)
            list_button_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
            list_button_frame.columnconfigure(0, weight=1)
            list_button_frame.columnconfigure(1, weight=1)

            self.button_edit_question = ttk.Button(list_button_frame, text="Load for Editing", command=self.edit_question, state=tk.DISABLED)
            self.button_edit_question.grid(row=0, column=0, sticky="ew", padx=(0, 2))
            Tooltip(self.button_edit_question, "Load the selected question from the list into the editor.")

            self.button_delete_question = ttk.Button(list_button_frame, text="Delete Question(s)", command=self.delete_selected_questions)
            self.button_delete_question.grid(row=0, column=1, sticky="ew", padx=(2, 0))
            Tooltip(self.button_delete_question, "Delete the selected question(s) from the list.")

            self.button_load_xml = ttk.Button(list_button_frame, text="Load XML File", command=self.load_xml_file)
            self.button_load_xml.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
            Tooltip(self.button_load_xml, "Load questions from a Moodle XML file.")

            # Right side: Question Details
            self.details_frame = ttk.Frame(self.main_frame)
            self.details_frame.grid(row=0, column=1, sticky="nsew")
            self.details_frame.columnconfigure(1, weight=1)

            self.setup_questionBuilder_UI()
            debug_logger.debug("User interface setup complete")
        except Exception as e:
            logging.error("Error initializing the application", exc_info=True)
            debug_logger.debug("Brutal error. Cannot initialize application.")

    def setup_questionBuilder_UI(self):
        try:
            # Add a heading to the details frame
            ttk.Label(self.details_frame, text="Question Details", font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10), padx=10)

            def validate_points(value_if_allowed):
                if value_if_allowed == "" or value_if_allowed.isdigit():
                    return True
                try:
                    float(value_if_allowed)
                    return True
                except ValueError:
                    return False
            vcmd = (self.root.register(validate_points), '%P')
            
            self.label_question_type = ttk.Label(self.details_frame, text="Select Question Type:", anchor='e')
            self.label_question_type.grid(row=2, column=0, padx=10, pady=5, sticky='e')
            self.question_type_var = tk.StringVar(value="Multiple Choice")
            self.dropdown_question_type = ttk.Combobox(self.details_frame, textvariable=self.question_type_var, values=["Multiple Choice", "True/False", "Short Answer", "Essay", "Cloze"])
            self.dropdown_question_type.bind("<<ComboboxSelected>>", lambda event: self.update_ui_for_question_type(self.question_type_var.get()))
            self.dropdown_question_type.state(["readonly"])  # Make it read-only to simulate an OptionMenu behavior
            self.dropdown_question_type.grid(row=2, column=1, padx=10, pady=5, sticky='w')
            #Tooltip(self.dropdown_question_type, "Select the type of question you want to create. The controls will update based on the selected question type.")
            debug_logger.debug("Question type dropdown initialized.")
            self.label_question_name = ttk.Label(self.details_frame, text="Enter Question Title:", anchor='e')
            self.label_question_name.grid(row=3, column=0, padx=10, pady=5, sticky='e')
            self.entry_question_name = ttk.Entry(self.details_frame, width=50)
            self.entry_question_name.grid(row=3, column=1, padx=10, pady=5, columnspan=2, sticky='we')
            Tooltip(self.entry_question_name, "Enter a title for the question. This will be displayed as the Question Name in Moodle.\n\nNote that Question Name is NOT the same thing as the text of the question. Question Names are purely cosmetic and only seeen by the instructor.")
            debug_logger.debug("Question name input field initialized.")
            self.label_question_text = ttk.Label(self.details_frame, text="Enter Question Text:", anchor='e')
            self.label_question_text.grid(row=4, column=0, padx=10, pady=5, sticky='e')
            self.entry_question_text = tk.Text(self.details_frame, width=50, height=4)
            self.entry_question_text.grid(row=4, column=1, padx=10, pady=5, sticky='we', columnspan=2)
            self.entry_question_text.bind("<Tab>", lambda e: self.entry_question_text.tk_focusNext().focus())
            self.entry_question_text.bind("<Shift-Tab>", lambda e: self.entry_question_text.tk_focusPrev().focus())
            Tooltip(self.entry_question_text, "Enter the text of the question.")
            debug_logger.debug("Question text input field initialized.")
            self.label_points = ttk.Label(self.details_frame, text="Point Value (default is 1):", anchor='e')
            self.label_points.grid(row=6, column=0, padx=10, pady=5, sticky='e')
            self.entry_points = ttk.Entry(self.details_frame, width=10, validate='key', validatecommand=vcmd)
            self.entry_points.grid(row=6, column=1, sticky='w', padx=10, pady=5)
            self.entry_points.insert(0, "1")  # Default value for points is 1
            Tooltip(self.entry_points, "Enter the point value for this question.\n\nThis value is used as the default grade for the question in Moodle. This isn't really necessary to set, depending on how your quiz is going to be configured.\nMoodle figures out how many points each question should be worth based on the Maximum Grade you set for the quiz.\n\nIn short, this is purely personal preference.")
            debug_logger.debug("Points input field initialized.")
##Multiple Choice Question UI
            
            self.label_mcq_options = ttk.Label(self.details_frame, text="Possible Choices:", anchor='e')
            self.label_mcq_options.grid(row=7, column=0, padx=10, pady=5, sticky='ne')

            self.mcq_options_frame = ttk.Frame(self.details_frame)
            self.mcq_options_frame.grid(row=7, column=1, padx=10, pady=5, columnspan=2, sticky='we')

            # Add buttons above the entries
            self.mcq_buttons_frame = ttk.Frame(self.mcq_options_frame)
            self.mcq_buttons_frame.pack(side=tk.TOP, fill='x', pady=(0,2))

            self.add_mcq_option_button = ttk.Button(self.mcq_buttons_frame, text="Add Choice", command=self._add_mcq_option_entry)
            self.add_mcq_option_button.pack(side=tk.LEFT, padx=(0,5))

            self.remove_mcq_option_button = ttk.Button(self.mcq_buttons_frame, text="Remove Choice", command=self._remove_last_mcq_option_entry)
            self.remove_mcq_option_button.pack(side=tk.LEFT)

            # Add a label to indicate what the checkboxes do
            self.mcq_checkbox_label = ttk.Label(self.mcq_options_frame, text="Check for correct answer(s):", anchor='w', font=("Arial", 9, "italic"))
            self.mcq_checkbox_label.pack(side=tk.TOP, anchor='w', pady=(0,2))

            for _ in range(4):
                self._add_mcq_option_entry()
            
            debug_logger.debug("Multiple choice options input field initialized.")
##End Multiple Choice Question UI
            self.label_short_answer_correct = ttk.Label(self.details_frame, text="Enter Correct Short Answer:", anchor='e')
            self.label_short_answer_correct.grid(row=9, column=0, padx=10, pady=5, sticky='e')
            self.entry_short_answer_correct = ttk.Entry(self.details_frame, width=50)
            self.entry_short_answer_correct.grid(row=9, column=1, padx=10, pady=5)
            Tooltip(self.entry_short_answer_correct, "Enter the correct answer for the short answer question.\n\nShort Answer questions are very sensitive to spelling and punctuation. \nBe sure to enter the correct answer EXACTLY as you want it to be entered by students.\n\nWildcards are supported: you can replace a character with an asterisk * to act as a placeholder for any possible character that could be used. \nThis can let you account for alternative spellings.\n\nIf the question doesn't have a definitive answer, you should use the Essay question type instead. \nEssay questions are open-ended and give the student a blank text box to write in.")
            debug_logger.debug("Short answer input field initialized.")
            self.label_tf_answer = ttk.Label(self.details_frame, text="Select True/False:", anchor='e')
            self.label_tf_answer.grid(row=10, column=0, padx=10, pady=5, sticky='e')
            self.tf_var = tk.StringVar(value="True")
            self.radio_true = ttk.Radiobutton(self.details_frame, text="True", variable=self.tf_var, value="True")
            self.radio_true.grid(row=10, column=1, sticky='w')
            self.radio_false = ttk.Radiobutton(self.details_frame, text="False", variable=self.tf_var, value="False")
            self.radio_false.grid(row=10, column=1, sticky='e')
            Tooltip(self.radio_true, "Select if the answer is True.")
            Tooltip(self.radio_false, "Select if the answer is False.")
            debug_logger.debug("True/False radio buttons initialized.")
            self.button_cloze_editor = ttk.Button(self.details_frame, text="Open Cloze Editor", command=self.cloze_editor)
            self.button_cloze_editor.grid(row=5, column=1, padx=10, pady=5, columnspan=2, sticky='we')
            
            # --- Action Buttons ---
            button_frame = ttk.Frame(self.details_frame)
            button_frame.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(15, 0), padx=10)
            button_frame.columnconfigure(0, weight=1)
            button_frame.columnconfigure(1, weight=1)
            button_frame.columnconfigure(2, weight=1)

            self.button_add_question = ttk.Button(button_frame, text="Add Question", command=self.add_question)
            self.button_add_question.grid(row=0, column=0, columnspan=3, sticky="ew", padx=(0, 2))
            Tooltip(self.button_add_question, "Add the current question to the list or update the selected one.")

            self.button_save_xml = ttk.Button(button_frame, text="Save as XML", command=self.save_as_xml)
            self.button_save_xml.grid(row=1, column=0, columnspan=4, pady=(5,0), sticky='ew')
            Tooltip(self.button_save_xml, "Click to save all the questions in the list as a Moodle XML file.")

            self.update_ui_for_question_type("Multiple Choice")
            debug_logger.debug("UI finished initializing. Setting initial question type.")
        except Exception as e:
            logging.error("Error setting up the user interface", exc_info=True)
            debug_logger.debug("UI Error. See error_log.txt for details.")

####################################################################################################################################
## FUNCTIONALITY
####################################################################################################################################
    def on_question_select(self, event):
        if self.listbox_questions.curselection():
            self.button_edit_question.config(state=tk.NORMAL)
        else:
            self.button_edit_question.config(state=tk.DISABLED)
    def update_ui_for_question_type(self, question_type):
        try:
            self.label_mcq_options.grid()
            self.mcq_options_frame.grid()
            self.label_short_answer_correct.grid()
            self.entry_short_answer_correct.grid()
            self.label_tf_answer.grid()
            self.radio_true.grid()
            self.radio_false.grid()
            self.button_cloze_editor.grid()
            self.button_cloze_editor.grid_remove()
            self.label_mcq_options.grid_remove()
            self.mcq_options_frame.grid_remove()
            self.label_short_answer_correct.grid_remove()
            self.entry_short_answer_correct.grid_remove()
            self.label_tf_answer.grid_remove()
            self.radio_true.grid_remove()
            self.radio_false.grid_remove()
            if question_type == "Multiple Choice":
                self.label_mcq_options.grid(row=7, column=0, padx=10, pady=5, sticky='ne')
                self.mcq_options_frame.grid(row=7, column=1, padx=10, pady=5, columnspan=2, sticky='we')
                debug_logger.debug("QuestionType Multiple Choice selected.")
            elif question_type == "True/False":
                self.label_tf_answer.grid(row=10, column=0, padx=10, pady=5, sticky='e')
                self.radio_true.grid(row=10, column=1, sticky='w')
                self.radio_false.grid(row=10, column=1, sticky='e')
                debug_logger.debug("QuestionType True/False selected.")
            elif question_type == "Short Answer":
                self.label_short_answer_correct.grid(row=9, column=0, padx=10, pady=5, sticky='e')
                self.entry_short_answer_correct.grid(row=9, column=1, padx=10, pady=5)
                debug_logger.debug("QuestionType Short Answer selected.")
            elif question_type == "Essay":
                debug_logger.debug("QuestionType Essay selected.")
            elif question_type == "Cloze":
                self.button_cloze_editor.grid(row=5, column=1, padx=10, pady=5, columnspan=2, sticky='we')
                debug_logger.debug("QuestionType Cloze selected.")
        except Exception as e:
            logging.error("Error updating UI for question type", exc_info=True)
            debug_logger.debug("UI Error. See error_log.txt for details.")
    def add_question(self):
        try:
            question_type = self.question_type_var.get()
            question_name = self.entry_question_name.get()
            question_text = self.entry_question_text.get("1.0", tk.END).strip()
            points = self.entry_points.get()
            points = float(points) if points else 1.0  # Default to 1 point if not specified
            if question_type == "Multiple Choice":
                options = [entry.get().strip() for entry, var in self.mcq_option_entries if entry.get().strip()]
                correct_options = [idx + 1 for idx, (entry, var) in enumerate(self.mcq_option_entries) if var.get()]
                if question_name and question_text and options and correct_options:
                    question = {
                        "type": "Multiple Choice",
                        "name": question_name,
                        "text": question_text,
                        "options": options,
                        "correct": correct_options,
                        "points": points
                    }
                else:
                    messagebox.showwarning("Input Error", "Please enter the question name, text, options, and correct answer(s).")
                    return
            elif question_type == "True/False":
                tf_answer = self.tf_var.get()
                if question_name and question_text:
                    question = {
                        "type": "True/False",
                        "name": question_name,
                        "text": question_text,
                        "answer": tf_answer,
                        "points": points
                    }
                else:
                    messagebox.showwarning("Input Error", "Please enter the question name and text.")
                    return
            elif question_type == "Short Answer":
                correct_answer = self.entry_short_answer_correct.get()
                if question_name and question_text and correct_answer:
                    question = {
                        "type": "Short Answer",
                        "name": question_name,
                        "text": question_text,
                        "correct_answer": correct_answer,
                        "points": points
                    }
                else:
                    messagebox.showwarning("Input Error", "Please enter the question name, text, and correct answer.")
                    return
            elif question_type == "Essay":
                if question_name and question_text:
                    question = {
                        "type": "Essay",
                        "name": question_name,
                        "text": question_text,
                        "points": points
                    }
                else:
                    messagebox.showwarning("Input Error", "Please enter the question name and text.")
                    return
            elif question_type == "Cloze":
                if question_name and question_text:
                    question = {
                        "type": "Cloze",
                        "name": question_name,
                        "text": question_text,
                        "points": points
                    }
                else:
                    messagebox.showwarning("Input Error", "Please enter the question name and text.")
                    return
            if self.edit_mode:
                self.questions[self.edit_index] = question
                self.edit_mode = False
                self.edit_index = None
                self.button_add_question.config(text="Add Question")
                self.button_delete_question.config(state=tk.NORMAL)
            else:
                self.questions.append(question)
                debug_logger.debug(f"Added question: {question}")
            self.update_question_list()
            self.clear_entries()
        except Exception as e:
            logging.error("Error adding question", exc_info=True)
    def clear_entries(self):
        try:
            self.entry_question_name.delete(0, tk.END)
            self.entry_question_text.delete("1.0", tk.END)
            self.entry_points.delete(0, tk.END)
            self.entry_points.insert(0, "1")
            
            # --- Rebuild MCQ Frame ---
            # Destroy old widgets
            for child in self.mcq_options_frame.winfo_children():
                child.destroy()
            self.mcq_option_entries.clear()

            # Re-create buttons
            buttons_frame = ttk.Frame(self.mcq_options_frame)
            buttons_frame.pack(side=tk.TOP, fill='x', pady=(0, 2))
            add_button = ttk.Button(buttons_frame, text="Add Choice", command=self._add_mcq_option_entry)
            add_button.pack(side=tk.LEFT, padx=(0, 5))
            remove_button = ttk.Button(buttons_frame, text="Remove Choice", command=self._remove_last_mcq_option_entry)
            remove_button.pack(side=tk.LEFT)
            
            # Re-create label
            ttk.Label(self.mcq_options_frame, text="Check for correct answer(s):", anchor='w', font=("Arial", 9, "italic")).pack(side=tk.TOP, anchor='w', pady=(0,2))

            # Re-create initial 4 entries
            for _ in range(4):
                self._add_mcq_option_entry()

            self.entry_short_answer_correct.delete(0, tk.END)
            self.edit_mode = False
            self.edit_index = None
            self.button_add_question.config(text="Add Question")
            debug_logger.debug("Cleared all input fields.")
        except Exception as e:
            logging.error("Error clearing entries", exc_info=True)
    def delete_selected_questions(self):
        try:
            selected_indices = list(self.listbox_questions.curselection())
            selected_indices.reverse()
            for index in selected_indices:
                del self.questions[index]
            self.update_question_list()
            debug_logger.debug(f"Deleted questions at indices: {selected_indices}")
            self.on_question_select(None)
        except Exception as e:
            logging.error("Error deleting selected questions", exc_info=True)
    def update_question_list(self):
        try:
            self.listbox_questions.delete(0, tk.END)
            type_map = {
                "Multiple Choice": "Multichoice",
                "True/False": "T/F",
                "Short Answer": "ShortAns",
            }
            for question in self.questions:
                display_type = type_map.get(question['type'], question['type'])
                display_text = f"{display_type}: {question['name']} - {question['text']} (Points: {question['points']})"
                self.listbox_questions.insert(tk.END, display_text)
            self.sync_loaded_questions()
        except Exception as e:
            logging.error("Error updating question list", exc_info=True)

    def replace_questions(self, questions):
        try:
            self.questions = [copy.deepcopy(question) for question in questions]
            self.update_question_list()
        except Exception as e:
            logging.error("Error replacing questions", exc_info=True)

    def sync_loaded_questions(self):
        try:
            main_window = getattr(self, "main_window_ref", None)
            if main_window and hasattr(main_window, "quiz_tab"):
                main_window.quiz_tab.update_loaded_questions_from_question_builder(self.questions)
        except Exception as e:
            logging.error("Error syncing loaded questions", exc_info=True)
    def edit_question(self):
        try:
            selected_indices = list(self.listbox_questions.curselection())
            if not selected_indices:
                return
            if len(selected_indices) != 1:
                messagebox.showwarning("Edit Error", "Please select exactly one question to edit.")
                return
            index = selected_indices[0]
            question = self.questions[index]
            self.question_type_var.set(question['type'])
            self.update_ui_for_question_type(question['type'])
            self.entry_question_name.delete(0, tk.END)
            self.entry_question_name.insert(0, question['name'])
            self.entry_question_text.delete("1.0", tk.END)
            self.entry_question_text.insert("1.0", question['text'])
            self.entry_points.delete(0, tk.END)
            self.entry_points.insert(0, str(question['points']))
            if question['type'] == "Multiple Choice":
                # Remove all child widgets from mcq_options_frame to clear old entries and checkboxes
                for child in self.mcq_options_frame.winfo_children():
                    child.destroy()
                self.mcq_option_entries.clear()

                # Re-create the buttons
                buttons_frame = ttk.Frame(self.mcq_options_frame)
                buttons_frame.pack(side=tk.TOP, fill='x', pady=(0, 2))
                add_button = ttk.Button(buttons_frame, text="Add Choice", command=self._add_mcq_option_entry)
                add_button.pack(side=tk.LEFT, padx=(0, 5))
                remove_button = ttk.Button(buttons_frame, text="Remove Choice", command=self._remove_last_mcq_option_entry)
                remove_button.pack(side=tk.LEFT)
                
                # Re-create the label
                ttk.Label(self.mcq_options_frame, text="Check for correct answer(s):", anchor='w', font=("Arial", 9, "italic")).pack(side=tk.TOP, anchor='w', pady=(0,2))

                for idx, option in enumerate(question['options']):
                    frame = ttk.Frame(self.mcq_options_frame)
                    frame.pack(side=tk.TOP, pady=2, fill='x')
                    entry = ttk.Entry(frame, width=40)
                    entry.insert(0, option)
                    entry.pack(side=tk.LEFT, fill='x', expand=True)
                    var = tk.BooleanVar(value=(idx+1 in question['correct']))
                    checkbox = ttk.Checkbutton(frame, variable=var)
                    checkbox.pack(side=tk.LEFT, padx=5)
                    self.mcq_option_entries.append((entry, var))
            elif question['type'] == "True/False":
                self.tf_var.set(question['answer'])
            elif question['type'] == "Short Answer":
                self.entry_short_answer_correct.delete(0, tk.END)
                self.entry_short_answer_correct.insert(0, question['correct_answer'])
            self.edit_mode = True
            self.edit_index = index
            self.button_add_question.config(text="Update Question")
            self.button_delete_question.config(state=tk.DISABLED)
        except Exception as e:
            logging.error("Error editing question", exc_info=True)


####################################################################################################################################
## Saving and Exporting the XML
####################################################################################################################################
    def _add_mcq_option_entry(self, option_text="", checked=False):
        frame = ttk.Frame(self.mcq_options_frame)
        frame.pack(side=tk.TOP, pady=2, fill='x')
        entry = ttk.Entry(frame, width=40)
        entry.pack(side=tk.LEFT, fill='x', expand=True)
        if option_text:
            entry.insert(0, option_text)
        var = tk.BooleanVar(value=checked)
        checkbox = ttk.Checkbutton(frame, variable=var)
        checkbox.pack(side=tk.LEFT, padx=5)
        self.mcq_option_entries.append((entry, var))

    def _remove_last_mcq_option_entry(self):
        if self.mcq_option_entries:
            entry, var = self.mcq_option_entries.pop()
            entry.master.destroy()

    def add_mcq_option_entry_in_edit(self):
        frame = ttk.Frame(self.mcq_options_frame)
        frame.pack(side=tk.TOP, pady=2, fill='x')
        entry = ttk.Entry(frame, width=40)
        entry.pack(side=tk.LEFT, fill='x', expand=True)
        var = tk.BooleanVar(value=False)
        checkbox = ttk.Checkbutton(frame, variable=var)
        checkbox.pack(side=tk.LEFT, padx=5)
        self.mcq_option_entries.append((entry, var))

    def load_xml_file(self):
        try:
            file_path = filedialog.askopenfilename(
                title="Select a Moodle XML file",
                filetypes=[("XML files", "*.xml")]
            )
            if not file_path:
                return

            tree = ET.parse(file_path)
            root = tree.getroot()

            if root.tag != 'quiz':
                messagebox.showerror("Load Error", "Invalid Moodle XML file. The root element must be <quiz>.")
                return

            if self.questions:
                if not messagebox.askyesno("Confirm", "This will replace all current questions. Are you sure?"):
                    return

            loaded_questions = []
            category_text = ""

            for q_node in root.findall('question'):
                q_type_str = q_node.get('type')

                q_data = {}

                name_node = q_node.find('name/text')
                q_data['name'] = name_node.text.strip() if name_node is not None else "Untitled"

                text_node = q_node.find('questiontext/text')
                q_data['text'] = text_node.text.strip() if text_node is not None else ""

                points_node = q_node.find('defaultgrade')
                q_data['points'] = float(points_node.text) if points_node is not None else 1.0

                if q_type_str == 'category':
                    cat_text_node = q_node.find('category/text')
                    if cat_text_node is not None:
                        category_text = cat_text_node.text.replace('$course$/', '').strip()
                    continue

                elif q_type_str == 'multichoice':
                    q_data['type'] = "Multiple Choice"
                    options = []
                    correct = []
                    for i, ans_node in enumerate(q_node.findall('answer'), start=1):
                        ans_text = ans_node.find('text').text or ""
                        options.append(ans_text.strip())
                        if ans_node.get('fraction') == '100':
                            correct.append(i)
                    q_data['options'] = options
                    q_data['correct'] = correct

                elif q_type_str == 'truefalse':
                    q_data['type'] = "True/False"
                    for ans_node in q_node.findall('answer'):
                        if ans_node.get('fraction') == '100':
                            q_data['answer'] = "True" if ans_node.find('text').text.lower() == 'true' else "False"
                            break

                elif q_type_str == 'shortanswer':
                    q_data['type'] = "Short Answer"
                    ans_node = q_node.find('answer')
                    if ans_node is not None and ans_node.get('fraction') == '100':
                                               q_data['correct_answer'] = ans_node.find('text').text.strip()

                elif q_type_str == 'essay':
                    q_data['type'] = "Essay"
                
                elif q_type_str == 'cloze':
                    q_data['type'] = "Cloze"

                else:
                    continue # Skip unknown question types

                loaded_questions.append(q_data)

            self.questions = loaded_questions
            self.entry_category.delete(0, tk.END)
            self.entry_category.insert(0, category_text)
           
            self.update_question_list()
            self.clear_entries()
            messagebox.showinfo("Load Successful", f"Successfully loaded {len(loaded_questions)} questions from {os.path.basename(file_path)}.")
            debug_logger.debug(f"Loaded {len(loaded_questions)} questions from {file_path}")

        except ET.ParseError as e:
            messagebox.showerror("Load Error", f"Failed to parse XML file: {e}")
            logging.error("Error parsing XML file on load", exc_info=True)
        except Exception as e:
            messagebox.showerror("Load Error", f"An unexpected error occurred: {e}")
            logging.error("Error loading XML file", exc_info=True)

    def save_as_xml(self):
        try:
            if not self.questions:
                messagebox.showwarning("Save Error", "No questions to save.")
                return
            file_path = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML files", "*.xml")])
            if not file_path:
                return
            xml_content = self.create_xml_content()
            debug_logger.debug("Saving XML Structure.")
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(xml_content)
            messagebox.showinfo("Save Successful", f"Questions saved to {os.path.basename(file_path)}")
            debug_logger.debug(f"Questions saved to {os.path.basename(file_path)}")
        except Exception as e:
            logging.error("Error saving questions as XML", exc_info=True)
            debug_logger.debug("Save Error. See error_log.txt for details.")
    def create_xml_content(self):
        try:
            xml_content = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<quiz>\n"
            category_name = self.entry_category.get().strip()
            if category_name:
                xml_content += f"  <question type=\"category\">\n    <category>\n      <text>$course$/{category_name}</text>\n    </category>\n  </question>\n"
            for question in self.questions:
                if question['type'] == "Multiple Choice":
                    xml_content += f"  <question type=\"multichoice\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n"
                    for idx, option in enumerate(question['options'], start=1):
                        fraction = "100" if idx in question['correct'] else "0"
                        xml_content += f"    <answer fraction=\"{fraction}\">\n      <text>{option}</text>\n    </answer>\n"
                    xml_content += "    <shuffleanswers>1</shuffleanswers>\n  </question>\n"
                elif question['type'] == "True/False":
                    correct_value = "true" if question['answer'] == "True" else "false"
                    xml_content += f"  <question type=\"truefalse\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n    <answer fraction=\"100\">\n      <text>{correct_value}</text>\n    </answer>\n    <answer fraction=\"0\">\n      <text>{'false' if correct_value == 'true' else 'true'}</text>\n    </answer>\n  </question>\n"
                elif question['type'] == "Short Answer":
                    xml_content += f"  <question type=\"shortanswer\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n    <answer fraction=\"100\">\n      <text>{question['correct_answer']}</text>\n    </answer>\n  </question>\n"
                elif question['type'] == "Essay":
                    xml_content += f"   <question type=\"essay\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n  </question>\n"
                elif question['type'] == "Cloze":
                    xml_content += f" <question type=\"cloze\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n  </question>\n"
            xml_content += "</quiz>"
            return xml_content
        except Exception as e:
            logging.error("Error creating XML content", exc_info=True)
            return ""
        

####################################################################################################################################
## Cloze Editor 
####################################################################################################################################
    def cloze_editor(self):
        try:
            cloze_window = tk.Toplevel(self.root)
            cloze_window.title("Cloze Editor")
            cloze_window.geometry("355x255")
            # Make grid rows/columns expandable
            cloze_window.grid_rowconfigure(1, weight=1)
            cloze_window.grid_columnconfigure(0, weight=1)
            cloze_window.grid_columnconfigure(1, weight=1)
            #dropdown menu for the question type being built via Cloze
            cloze_window_label = tk.Label(cloze_window, text="Select Cloze Question Type:", anchor='w')
            cloze_window_label.grid(row=0, column=0, padx=10, pady=5, sticky='e')
            cloze_options = ["Multichoice", "Short Answer"]
            cloze_type_var = tk.StringVar(value="Multichoice")
            cloze_type_menu = ttk.Combobox(cloze_window, textvariable=cloze_type_var, values=cloze_options)
            cloze_type_menu.grid(row=0, column=1, padx=10, pady=5, sticky='w')
            cloze_type_menu.state(["readonly"])  # Make it read-only to simulate an OptionMenu behavior
            Tooltip(cloze_type_menu, "Select the type of cloze question you want to create.")
            debug_logger.debug("Cloze question type dropdown initialized.")
            # Weight input
            cloze_weight_label = tk.Label(cloze_window, text="Weight (relative to other Cloze snippets inside of this question):", anchor='w', wraplength=150)
            cloze_weight_label.grid(row=1, column=0, padx=10, pady=5, sticky='e')
            cloze_weight_entry = tk.Entry(cloze_window, width=10)
            cloze_weight_entry.grid(row=1, column=1, padx=10, pady=5, sticky='w')
            cloze_weight_entry.insert(0, "1")
            Tooltip(cloze_weight_entry, "Enter the weight for this cloze question snippet.\n\nFor example, if you have two cloze snippets with weights 2 and 4, the second will be worth twice the percentage of points as the first one, \neven if the question itself is only worth one point. \nThis does NOT affect the total score of the question, just how the subquestions have their points distributed.")
            # Correct answers
            correct_answers_frame = tk.LabelFrame(cloze_window, text="Correct Answer(s)")
            correct_answers_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky='we')
            correct_answer_entries = []

            def add_correct_answer():
                entry = tk.Entry(correct_answers_frame, width=30)
                entry.pack(padx=2, pady=2, fill='x')
                correct_answer_entries.append(entry)
                cloze_window.update_idletasks()
                # Grow window height by 30 pixels per new entry (adjust as needed)
                w = cloze_window.winfo_width()
                h = cloze_window.winfo_height()
                cloze_window.geometry(f"{w}x{h+30}")

            add_correct_button = tk.Button(correct_answers_frame, text="Add Correct Answer", command=add_correct_answer)
            add_correct_button.pack(padx=2, pady=2, fill='x')
            add_correct_answer()  # Add one by default

            # Wrong answers
            wrong_answers_frame = tk.LabelFrame(cloze_window, text="Wrong Answer(s)")
            wrong_answers_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky='we')
            wrong_answer_entries = []

            def add_wrong_answer():
                entry = tk.Entry(wrong_answers_frame, width=30)
                entry.pack(padx=2, pady=2, fill='x')
                wrong_answer_entries.append(entry)
                cloze_window.update_idletasks()
                w = cloze_window.winfo_width()
                h = cloze_window.winfo_height()
                cloze_window.geometry(f"{w}x{h+30}")

            add_wrong_button = tk.Button(wrong_answers_frame, text="Add Wrong Answer", command=add_wrong_answer)
            add_wrong_button.pack(padx=2, pady=2, fill='x')
            add_wrong_answer()  # Add one by default

            # Show/hide wrong answers based on cloze type
            def update_wrong_answers_visibility(*args):
                if cloze_type_var.get() == "Multichoice":
                    wrong_answers_frame.grid()
                else:
                    wrong_answers_frame.grid_remove()
            cloze_type_var.trace_add('write', update_wrong_answers_visibility)
            update_wrong_answers_visibility()

            def build_cloze_string():
                weight = cloze_weight_entry.get().strip() or "100"
                corrects = [e.get().strip() for e in correct_answer_entries if e.get().strip()]
                wrongs = [e.get().strip() for e in wrong_answer_entries if e.get().strip()]
                cloze_type = cloze_type_var.get().upper().replace(" ", "")
                # Build answer string
                answer_parts = []
                if corrects:
                    answer_parts.append(f"={corrects[0]}")
                    for c in corrects[1:]:
                        answer_parts.append(f"~={c}")
                for w in wrongs:
                    answer_parts.append(f"~{w}")
                answer_str = "".join(answer_parts)
                return f"{{{weight}:{cloze_type}:{answer_str}}}"
                #the line above is why multiple choice questions are named "multichoice" - cloze only knows multichoice and the string is built via looking at the cloze_type_var value

            def insert_cloze():
                cloze_string = build_cloze_string()
                if cloze_string:
                    self.entry_question_text.insert(tk.END, f"\n\n{cloze_string}".strip())
                    cloze_window.destroy()
                    debug_logger.debug("Cloze content inserted into question text.")
                else:
                    messagebox.showwarning("Cloze Editor", "Please enter some content or answers before inserting.")
            insert_button = tk.Button(cloze_window, text="Insert Cloze Content", command=insert_cloze)
            insert_button.grid(row=4, column=0, columnspan=2, pady=10)
            debug_logger.debug("Cloze editor window opened.")
        except Exception as e:
            logging.error("Error opening Cloze editor", exc_info=True)

class quizBuilder:
    def __init__(self, parent):
        self.root = parent
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.main_window_ref = None
        tk.Label(self.root, text="Quiz Title").grid(row=0, column=0, padx=10, pady=10, sticky='e')
        self.quiz_title_entry = tk.Entry(self.root, width=50)
        self.quiz_title_entry.grid(row=0, column=1, padx=10, pady=10, sticky='we')
        tk.Label(self.root, text="Quiz Description").grid(row=1, column=0, padx=10, pady=10, sticky='e')
        self.quiz_description_entry = tk.Text(self.root, width=50, height=4)
        self.quiz_description_entry.grid(row=1, column=1, padx=10, pady=10, sticky='we')
        tk.Label(self.root, text="Display Description on Course Page").grid(row=2, column=0, padx=10, pady=10, sticky='we')
        # Create a BooleanVar to hold the state of the checkbox
        self.display_description_var = tk.BooleanVar()
        self.display_description_boolean = tk.Checkbutton(self.root, variable=self.display_description_var)
        self.display_description_boolean.grid(row=2, column=1, padx=10, pady=10, sticky='w')
        # The line below was creating a second, unused checkbox. It has been removed.
        tk.Label(self.root, text="Point Value").grid(row=3, column=0, padx=10, pady=10, sticky='e')
        self.point_value_var = tk.StringVar(value="100")
        self.point_value_entry = tk.Entry(self.root, width=10, textvariable=self.point_value_var, validate="key")
        self.point_value_entry['validatecommand'] = (self.root.register(lambda v: v.isdigit() or v == ""), '%P')
        self.point_value_entry.grid(row=3, column=1, padx=10, pady=10, sticky="w")
        #add a date picker and two dropdowns for hours and minutes
        tk.Label(self.root, text="Open the quiz").grid(row=4, column=0, padx=10, pady=10, sticky='e')
        # Store the DateEntry widget in an instance variable
        self.cal_open = DateEntry(self.root, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='y-mm-dd')
        self.cal_open.grid(row=4, column=1, padx=10, pady=10, sticky='w')
        self.hours_open = [f"{i:02d}" for i in range(24)]
        self.minutes_open = [f"{i:02d}" for i in range(0, 60, 5)]
        self.hour_open_var = tk.StringVar(value="00")
        self.minute_open_var = tk.StringVar(value="00")
        # Correctly pass the instance variables for textvariable and values
        hour_open_menu = ttk.Combobox(self.root, textvariable=self.hour_open_var, values=self.hours_open, width=3)
        hour_open_menu.grid(row=4, column=1, padx=(120,0), pady=10, sticky='w')
        hour_open_menu.state(["readonly"])
        # Correctly pass the instance variables for textvariable and values
        minute_open_menu = ttk.Combobox(self.root, textvariable=self.minute_open_var, values=self.minutes_open, width=3)
        minute_open_menu.grid(row=4, column=1, padx=(170,0), pady=10, sticky='w')
        minute_open_menu.state(["readonly"])
        # This AM/PM menu was not being stored or used, so it's removed for now to avoid confusion.
        # If 12-hour format is needed later, it should be properly implemented.
        tk.Label(self.root, text="Close the quiz").grid(row=5, column=0, padx=10, pady=10, sticky='e')
        # Store the DateEntry widget in an instance variable
        self.cal_close = DateEntry(self.root, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='y-mm-dd')
        self.cal_close.grid(row=5, column=1, padx=10, pady=10, sticky='w')
        self.hours_close = [f"{i:02d}" for i in range(24)]
        self.minutes_close = [f"{i:02d}" for i in range(0, 60, 5)]
        self.hour_close_var = tk.StringVar(value="00")
        self.minute_close_var = tk.StringVar(value="00")
        # Correctly pass the instance variables for textvariable and values
        hour_close_menu = ttk.Combobox(self.root, textvariable=self.hour_close_var, values=self.hours_close, width=3)
        hour_close_menu.grid(row=5, column=1, padx=(120,0), pady=10, sticky='w')
        hour_close_menu.state(["readonly"])
        # Correctly pass the instance variables for textvariable and values
        minute_close_menu = ttk.Combobox(self.root, textvariable=self.minute_close_var, values=self.minutes_close, width=3)
        minute_close_menu.grid(row=5, column=1, padx=(170,0), pady=10, sticky='w')
        minute_close_menu.state(["readonly"])
        # This AM/PM menu was not being stored or used, so it's removed for now.
        self.time_limit_label = tk.Label(self.root, text="Time limit").grid(row=6, column=0, padx=10, pady=10, sticky='e')
        self.time_limit_var = tk.StringVar(value="0")
        self.time_limit_entry = tk.Entry(self.root, width=4, textvariable=self.time_limit_var, validate="key")
        self.time_limit_entry['validatecommand'] = (self.root.register(lambda v: v.isdigit() or v == ""), '%P')
        self.time_limit_entry.grid(row=6, column=1, padx=10, pady=10, sticky="w")
        self.attempts_allowed_label = tk.Label(self.root, text="Attempts allowed").grid(row=7, column=0, padx=10, pady=10, sticky='e')
        self.attempts_allowed_var = tk.StringVar(value="1")
        self.attempts_allowed_entry = tk.Entry(self.root, width=4, textvariable=self.attempts_allowed_var, validate="key")
        self.attempts_allowed_entry['validatecommand'] = (self.root.register(lambda v: v.isdigit() or v == ""), '%P')
        self.attempts_allowed_entry.grid(row=7, column=1, padx=10, pady=10, sticky="w")
        # Label + help for loaded questions
        self.loaded_questions_label_frame = tk.Frame(self.root)
        self.loaded_questions_label_frame.grid(row=8, column=0, columnspan=2, padx=10, sticky='we')
        self.label_loaded_questions = tk.Label(self.loaded_questions_label_frame, text="Saved Quizzes")
        self.label_loaded_questions.pack(side=tk.LEFT)
        self.label_loaded_help = tk.Label(self.loaded_questions_label_frame, text=" ?", fg="blue", cursor="hand2")
        self.label_loaded_help.pack(side=tk.LEFT, padx=(6,0))
        Tooltip(
            self.label_loaded_help,
            "This list stores quizzes that are ready for export.\n\nUse the Add button to capture the current quiz setup, then export all saved quizzes at once.",
        )
        # listbox to show saved quizzes
        self.root.grid_rowconfigure(10, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self.listbox_quizzes = tk.Listbox(self.root)
        self.listbox_quizzes.grid(row=10, column=0, columnspan=3, padx=10, pady=6, sticky='nsew')
        # storage for quizzes staged for export and the latest question set from the builder
        self.saved_quizzes: List[Dict[str, Any]] = []
        self.current_question_set: List[Dict[str, Any]] = []

        self.import_xml_btn = tk.Button(self.root, text="Import Question XML File", state=tk.DISABLED)
        self.import_xml_btn.grid(row=9, column=0, padx=10, pady=10, sticky='we')


        # Save Quiz button above listbox
        self.save_quiz_btn = tk.Button(self.root, text="Save Quiz", command=self.add_quiz_to_export_list)
        self.save_quiz_btn.grid(row=8, column=0, columnspan=2, padx=10, pady=6, sticky='we')

        tk.Button(self.root, text="Export Quizzes (.mbz)", command=self.export_quiz_mbz)\
            .grid(row=11, column=0, columnspan=2, padx=10, pady=10, sticky='')

        tk.Button(self.root, text="Debug: Show Variables", command=self.show_debug_info)\
            .grid(row=9, column=1, padx=10, pady=5, sticky='we')

        pass

    def add_quiz_to_export_list(self):
        try:
            quiz_name = (self.quiz_title_entry.get() or "Quiz").strip()
            intro_html = self.quiz_description_entry.get("1.0", tk.END).strip()

            qb = self.get_question_builder()
            if qb is not None:
                questions = [copy.deepcopy(question) for question in qb.questions]
                category_name = qb.entry_category.get().strip() or "Default category"
            else:
                questions = [copy.deepcopy(question) for question in self.current_question_set]
                category_name = "Default category"

            # if not questions:
            #     messagebox.showwarning(
            #         "Save Quiz",
            #         "There are no questions available to save. Create or import questions before adding the quiz to the export list.",
            #     )
            #     return

            quiz_payload = {
                "quiz_name": quiz_name or f"Quiz {len(self.saved_quizzes) + 1}",
                "intro_html": intro_html,
                "category_name": category_name,
                "questions": questions,
            }

            self.saved_quizzes.append(quiz_payload)
            self.update_saved_quiz_listbox()
            messagebox.showinfo(
                "Save Quiz",
                f"'{quiz_payload['quiz_name']}' was added to the export list.",
            )
        except Exception as e:
            messagebox.showerror("Save Quiz", f"An error occurred while saving the quiz: {e}")
            logging.error("Error adding quiz to export list", exc_info=True)

    def show_debug_info(self):
        """Gathers and displays the current values of all variables in the quizBuilder tab."""
        try:
            # Gather values from all input widgets
            quiz_title = self.quiz_title_entry.get()
            quiz_description = self.quiz_description_entry.get("1.0", tk.END).strip()
            display_description = self.display_description_var.get()
            point_value = self.point_value_entry.get()
            open_date = self.cal_open.get()
            open_hour = self.hour_open_var.get()
            open_minute = self.minute_open_var.get()
            close_date = self.cal_close.get()
            close_hour = self.hour_close_var.get()
            close_minute = self.minute_close_var.get()
            time_limit = self.time_limit_entry.get()
            attempts_allowed = self.attempts_allowed_entry.get()
            num_loaded_questions = len(self.current_question_set)
            num_saved_quizzes = len(self.saved_quizzes)

            # Format the information into a string
            debug_message = (
                f"Quiz Title: {quiz_title}\n"
                f"Quiz Description: {quiz_description}\n"
                f"Display Description: {display_description}\n"
                f"Point Value: {point_value}\n\n"
                f"Open Date: {open_date}\n"
                f"Open Time: {open_hour}:{open_minute}\n\n"
                f"Close Date: {close_date}\n"
                f"Close Time: {close_hour}:{close_minute}\n\n"
                f"Time Limit: {time_limit}\n"
                f"Attempts Allowed: {attempts_allowed}\n\n"
                f"Questions Available for Saving: {num_loaded_questions}\n"
                f"Quizzes Saved for Export: {num_saved_quizzes}"
            )

            # Display the information in a message box
            messagebox.showinfo("Quiz Builder Debug Info", debug_message)
            debug_logger.debug("Displayed quizBuilder debug info.")
        except Exception as e:
            messagebox.showerror("Debug Error", f"An error occurred while gathering debug info: {e}")
            logging.error("Error in show_debug_info", exc_info=True)

    def import_xml(self):
        # Functionality disabled
        pass

    def export_quiz_mbz(self):
        try:
            if not self.saved_quizzes:
                tk.messagebox.showwarning(
                    "Export",
                    "No quizzes have been saved. Use 'Add Quiz to Export List' before exporting.",
                )
                return

            # Clone the saved quizzes so the export routine can annotate module IDs without
            # mutating the UI state.
            export_payload = []
            moduleid_start = 5000
            for idx, quiz in enumerate(self.saved_quizzes):
                payload = copy.deepcopy(quiz)
                payload["moduleid"] = moduleid_start + idx
                export_payload.append(payload)

            mbz_bytes = build_quizzes_mbz(export_payload, moduleid_start=moduleid_start)

            # Save dialog
            path = filedialog.asksaveasfilename(
                defaultextension=".mbz",
                filetypes=[("Moodle Backup", "*.mbz"), ("Zip", "*.zip")],
                initialfile="quizzes.mbz",
            )
            if not path:
                return
            with open(path, "wb") as f:
                f.write(mbz_bytes)
            tk.messagebox.showinfo("Export", f"Exported Moodle backup with {len(self.saved_quizzes)} quiz(es):\n{os.path.basename(path)}")
        except Exception as e:
            tk.messagebox.showerror("Export Error", f"Failed to export .mbz: {e}")


    def update_saved_quiz_listbox(self):
        self.listbox_quizzes.delete(0, tk.END)
        for idx, quiz in enumerate(self.saved_quizzes, start=1):
            title = quiz.get("quiz_name") or f"Quiz {idx}"
            question_count = len(quiz.get("questions", []))
            self.listbox_quizzes.insert(tk.END, f"{idx}. {title} ({question_count} questions)")

    def update_loaded_questions_from_question_builder(self, questions):
        self.current_question_set = [copy.deepcopy(question) for question in questions]

    def get_question_builder(self):
        mw = getattr(self, "main_window_ref", None)
        if mw and hasattr(mw, "quiz_builder"):
            return mw.quiz_builder
        return None
class assignmentBuilder:
    def __init__(self, parent):
        self.root = parent
        assignment_name_label = tk.Label(self.root, text="Assignment Name").grid(row=0, column=0, padx=10, pady=10, sticky='e')
        assignment_name_entry = tk.Entry(self.root, width=50)
        assignment_name_entry.grid(row=0, column=1, padx=10, pady=10, sticky='we')
        self.assignment_name_entry = assignment_name_entry

        assignment_description_label = tk.Label(self.root, text="Assignment Description").grid(row=1, column=0, padx=10, pady=10, sticky='e')
        assignment_description_entry = tk.Text(self.root, width=50, height=4)
        assignment_description_entry.grid(row=1, column=1, padx=10, pady=10, sticky='we')
        self.assignment_description_entry = assignment_description_entry

        display_description_label = tk.Label(self.root, text="Display Description on Course Page").grid(row=2, column=0, padx=10, pady=10, sticky='w')
        display_description_boolean = tk.Checkbutton(self.root)
        display_description_boolean.grid(row=2, column=1, padx=10, pady=10, sticky='w')
        self.display_description_boolean = display_description_boolean

        point_value_label = tk.Label(self.root, text="Point Value").grid(row=3, column=0, padx=10, pady=10, sticky='e')
        point_value_entry = tk.Entry(self.root, width=10)
        point_value_entry.grid(row=3, column=1, padx=10, pady=10, sticky="w")
        self.point_value_entry = point_value_entry

        open_date_label = tk.Label(self.root, text="Open the assignment").grid(row=4, column=0, padx=10, pady=10, sticky='e')
        self.cal_open = DateEntry(self.root, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='y-mm-dd')
        self.cal_open.grid(row=4, column=1, padx=10, pady=10, sticky='w')
        hours = [f"{i:02d}" for i in range(24)]
        minutes = [f"{i:02d}" for i in range(0, 60, 5)]
        self.hour_var = tk.StringVar(value="00")
        self.minute_var = tk.StringVar(value="00")
        self.hour_menu = ttk.Combobox(self.root, textvariable=self.hour_var, values=hours, width=3)
        self.hour_menu.grid(row=4, column=1, padx=(120,0), pady=10, sticky='w')
        self.hour_menu.state(["readonly"])
        self.minute_menu = ttk.Combobox(self.root, textvariable=self.minute_var, values=minutes, width=3)
        self.minute_menu.grid(row=4, column=1, padx=(160,0), pady=10, sticky='w')
        self.minute_menu.state(["readonly"])
        self.am_pm_var = tk.StringVar(value="AM")
        self.am_pm_menu = ttk.Combobox(self.root, textvariable=self.am_pm_var, values=["AM", "PM"], width=3)
        self.am_pm_menu.grid(row=4, column=1, padx=(210,0), pady=10, sticky='w')
        self.am_pm_menu.state(["readonly"])
        # Close date/time widgets
        tk.Label(self.root, text="Close the assignment").grid(row=5, column=0, padx=10, pady=10, sticky='e')
        self.cal_close = DateEntry(self.root, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='y-mm-dd')
        self.cal_close.grid(row=5, column=1, padx=10, pady=10, sticky='w')
        self.hour_close_var = tk.StringVar(value="00")
        self.minute_close_var = tk.StringVar(value="00")
        self.hour_close_menu = ttk.Combobox(self.root, textvariable=self.hour_close_var, values=hours, width=3)
        self.hour_close_menu.grid(row=5, column=1, padx=(120,0), pady=10, sticky='w')
        self.hour_close_menu.state(["readonly"])
        self.minute_close_menu = ttk.Combobox(self.root, textvariable=self.minute_close_var, values=minutes, width=3)
        self.minute_close_menu.grid(row=5, column=1, padx=(170,0), pady=10, sticky='w')
        self.minute_close_menu.state(["readonly"])
        self.am_pm_close_var = tk.StringVar(value="AM")
        self.am_pm_close_menu = ttk.Combobox(self.root, textvariable=self.am_pm_close_var, values=["AM", "PM"], width=3)
        self.am_pm_close_menu.grid(row=5, column=1, padx=(220,0), pady=10, sticky='w')
        self.am_pm_close_menu.state(["readonly"])
        pass

    def get_assignment_data(self):
        data = {
            "name": self.assignment_name_entry.get().strip(),
            "description": self.assignment_description_entry.get("1.0", tk.END).strip(),
            "display_description": bool(self.display_description_boolean.var.get()) if hasattr(self.display_description_boolean, 'var') else False,
            "points": self.point_value_entry.get().strip(),
            "open_date": self.cal_open.get(),
            "open_hour": self.hour_var.get(),
            "open_minute": self.minute_var.get(),
            "open_am_pm": self.am_pm_var.get(),
            "close_date": self.cal_close.get(),
            "close_hour": self.hour_close_var.get(),
            "close_minute": self.minute_close_var.get(),
            "close_am_pm": self.am_pm_close_var.get(),
        }
        return data
class forumBuilder:
    def __init__(self, parent):
        self.root = parent
        forum_name_label = tk.Label(self.root, text="Forum Name").grid(row=0, column=0, padx=10, pady=10, sticky='e')
        forum_name_entry = tk.Entry(self.root, width=50)
        forum_name_entry.grid(row=0, column=1, padx=10, pady=10, sticky='we')
        self.forum_name_entry = forum_name_entry

        forum_description_label = tk.Label(self.root, text="Forum Description").grid(row=1, column=0, padx=10, pady=10, sticky='e')
        forum_description_entry = tk.Text(self.root, width=50, height=4)
        forum_description_entry.grid(row=1, column=1, padx=10, pady=10, sticky='we')
        self.forum_description_entry = forum_description_entry

        display_description_label = tk.Label(self.root, text="Display Description on Course Page").grid(row=2, column=0, padx=10, pady=10, sticky='w')
        display_description_boolean = tk.Checkbutton(self.root)
        display_description_boolean.grid(row=2, column=1, padx=10, pady=10, sticky='w')
        self.display_description_boolean = display_description_boolean

        point_value_label = tk.Label(self.root, text="Point Value").grid(row=3, column=0, padx=10, pady=10, sticky='e')
        point_value_entry = tk.Entry(self.root, width=10)
        point_value_entry.grid(row=3, column=1, padx=10, pady=10, sticky="w")
        self.point_value_entry = point_value_entry

        open_date_label = tk.Label(self.root, text="Open the forum").grid(row=4, column=0, padx=10, pady=10, sticky='e')
        self.cal_open = DateEntry(self.root, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='y-mm-dd')
        self.cal_open.grid(row=4, column=1, padx=10, pady=10, sticky='w')
        hours = [f"{i:02d}" for i in range(24)]
        minutes = [f"{i:02d}" for i in range(0, 60, 5)]
        self.hour_var = tk.StringVar(value="00")
        self.minute_var = tk.StringVar(value="00")
        self.hour_menu = ttk.Combobox(self.root, textvariable=self.hour_var, values=hours, width=3)
        self.hour_menu.grid(row=4, column=1, padx=(120,0), pady=10, sticky='w')
        self.hour_menu.state(["readonly"])
        self.minute_menu = ttk.Combobox(self.root, textvariable=self.minute_var, values=minutes, width=3)
        self.minute_menu.grid(row=4, column=1, padx=(160,0), pady=10, sticky='w')
        self.minute_menu.state(["readonly"])
        self.am_pm_var = tk.StringVar(value="AM")
        self.am_pm_menu = ttk.Combobox(self.root, textvariable=self.am_pm_var, values=["AM", "PM"], width=3)
        self.am_pm_menu.grid(row=4, column=1, padx=(210,0), pady=10, sticky='w')
        self.am_pm_menu.state(["readonly"])
        # Close date/time widgets
        tk.Label(self.root, text="Close the forum").grid(row=5, column=0, padx=10, pady=10, sticky='e')
        self.cal_close = DateEntry(self.root, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='y-mm-dd')
        self.cal_close.grid(row=5, column=1, padx=10, pady=10, sticky='w')
        self.hour_close_var = tk.StringVar(value="00")
        self.minute_close_var = tk.StringVar(value="00")
        self.hour_close_menu = ttk.Combobox(self.root, textvariable=self.hour_close_var, values=hours, width=3)
        self.hour_close_menu.grid(row=5, column=1, padx=(120,0), pady=10, sticky='w')
        self.hour_close_menu.state(["readonly"])
        self.minute_close_menu = ttk.Combobox(self.root, textvariable=self.minute_close_var, values=minutes, width=3)
        self.minute_close_menu.grid(row=5, column=1, padx=(170,0), pady=10, sticky='w')
        self.minute_close_menu.state(["readonly"])
        self.am_pm_close_var = tk.StringVar(value="AM")
        self.am_pm_close_menu = ttk.Combobox(self.root, textvariable=self.am_pm_close_var, values=["AM", "PM"], width=3)
        self.am_pm_close_menu.grid(row=5, column=1, padx=(220,0), pady=10, sticky='w')
        self.am_pm_close_menu.state(["readonly"])
        pass

    def get_forum_data(self):
        data = {
            "name": self.forum_name_entry.get().strip(),
            "description": self.forum_description_entry.get("1.0", tk.END).strip(),
            "display_description": bool(self.display_description_boolean.var.get()) if hasattr(self.display_description_boolean, 'var') else False,
            "points": self.point_value_entry.get().strip(),
            "open_date": self.cal_open.get(),
            "open_hour": self.hour_var.get(),
            "open_minute": self.minute_var.get(),
            "open_am_pm": self.am_pm_var.get(),
            "close_date": self.cal_close.get(),
            "close_hour": self.hour_close_var.get(),
            "close_minute": self.minute_close_var.get(),
            "close_am_pm": self.am_pm_close_var.get(),
        }
        return data

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = mainWindow(root)
        root.mainloop()
    except Exception as e:
        logging.error("Fatal error in main application loop", exc_info=True)