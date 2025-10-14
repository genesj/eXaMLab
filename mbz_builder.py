# mbz_builder.py
# Fixed Moodle activity backup (.mbz) builder for a single Quiz activity + question bank.
# Key fixes:
# 1) Files are written at the ZIP ROOT (no inner folder).
# 2) quiz.xml has an <activity ...> wrapper containing <quiz>.
# 3) module.xml, quiz.xml, folder name, and moodle_backup.xml use the SAME moduleid (CMID).
# 4) moodle_backup.xml puts <type>/<format> in <information><details><detail> and
#    includes <contents><activities><activity><directory>activities/quiz_<CMID></directory>.

import os, io, time, zipfile, random, string
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

# ---------- Utilities ----------
def _now_unix() -> int:
    return int(time.time())

def _uniq_suffix(n=6) -> str:
    import secrets, string
    alpha = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alpha) for _ in range(n))

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

def _et_to_bytes(root: ET.Element) -> bytes:
    _indent_xml(root)
    buf = io.BytesIO()
    buf.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
    buf.write(ET.tostring(root, encoding="utf-8"))
    return buf.getvalue()

# ---------- Question bank (questions.xml) ----------
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
        node = ET.SubElement(mc, tag); ET.SubElement(node, "text").text = ""
        ET.SubElement(mc, f"{tag}format").text = "1"
    ET.SubElement(mc, "shownumcorrect").text = "0"
    ET.SubElement(mc, "showstandardinstruction").text = "1"

def _add_truefalse_payload(qnode: ET.Element, q: Dict[str, Any]) -> None:
    correct_is_true = (str(q.get("answer", "True")).strip().lower() == "true")
    for label, frac in (("true", "1.0000000" if correct_is_true else "0.0000000"),
                        ("false", "1.0000000" if not correct_is_true else "0.0000000")):
        ans = ET.SubElement(qnode, "answer")
        ET.SubElement(ans, "fraction").text = frac
        at = ET.SubElement(ans, "answertext"); ET.SubElement(at, "text").text = label
        ET.SubElement(ans, "feedback").text = ""
        ET.SubElement(ans, "feedbackformat").text = "1"

def _add_shortanswer_payload(qnode: ET.Element, q: Dict[str, Any]) -> None:
    sa = ET.SubElement(qnode, "shortanswer")
    ET.SubElement(sa, "usecase").text = "0"
    ans = ET.SubElement(qnode, "answer")
    ET.SubElement(ans, "fraction").text = "1.0000000"
    at = ET.SubElement(ans, "answertext"); ET.SubElement(at, "text").text = q.get("correct_answer", "")
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
    Builds a minimal-yet-valid Moodle 4.x questions.xml with:
    - one category
    - one bank entry per question
    - one version per entry
    """
    root = ET.Element("question_categories")

    # Category (IDs are placeholders; Moodle remaps on restore)
    qcat = ET.SubElement(root, "question_category", {"id": "1000"})
    ET.SubElement(qcat, "name").text = category_name or "Default category"
    ET.SubElement(qcat, "idnumber").text = ""
    ET.SubElement(qcat, "contextid").text = "1"
    ET.SubElement(qcat, "contextlevel").text = "50"
    ET.SubElement(qcat, "contextinstanceid").text = "1"

    entries = ET.SubElement(root, "question_bank_entries")

    # Allocate entry ids deterministically from 2000
    for idx, q in enumerate(questions):
        entry_id = 2000 + idx
        e = ET.SubElement(entries, "question_bank_entry", {"id": str(entry_id)})
        ET.SubElement(e, "questioncategoryid").text = "1000"
        ET.SubElement(e, "idnumber").text = ""

        versions = ET.SubElement(e, "question_versions")
        v = ET.SubElement(versions, "question_version", {"id": str(3000 + idx)})
        ET.SubElement(v, "questionbankentryid").text = str(entry_id)
        ET.SubElement(v, "version").text = "1"
        ET.SubElement(v, "status").text = "ready"

        qnode = ET.SubElement(v, "question", {"id": str(4000 + idx)})
        qtype = _map_qtype(q.get("type"))
        ET.SubElement(qnode, "qtype").text = qtype
        ET.SubElement(qnode, "name").text = q.get("name", "Untitled")

        qt = ET.SubElement(qnode, "questiontext")
        ET.SubElement(qt, "text").text = q.get("text", "")
        ET.SubElement(qnode, "questiontextformat").text = "1"

        gf = ET.SubElement(qnode, "generalfeedback")
        ET.SubElement(gf, "text").text = ""
        ET.SubElement(qnode, "generalfeedbackformat").text = "1"

        ET.SubElement(qnode, "defaultmark").text = str(float(q.get("points", 1.0)))
        ET.SubElement(qnode, "penalty").text = "0.0000000"
        ET.SubElement(qnode, "stamp").text = f"q_{_uniq_suffix()}"
        now = str(_now_unix())
        ET.SubElement(qnode, "timecreated").text = now
        ET.SubElement(qnode, "timemodified").text = now
        ET.SubElement(qnode, "createdby").text = "2"
        ET.SubElement(qnode, "modifiedby").text = "2"

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

    return _et_to_bytes(root)

# ---------- Quiz activity (quiz.xml + module.xml) ----------
def build_quiz_activity_xml(
    moduleid: int,
    quiz_name: str,
    intro_html: str = "",
    entry_ids: list[int] | None = None,
    per_slot_maxmark: float = 1.0,
) -> bytes:
    activity_id = 260000
    quiz_id = 260000

    root = ET.Element("activity", {
        "id": str(activity_id),
        "moduleid": str(moduleid),
        "modulename": "quiz",
        "contextid": "1"
    })

    quiz = ET.SubElement(root, "quiz", {"id": str(quiz_id)})
    ET.SubElement(quiz, "name").text = quiz_name or "Quiz"
    intro = ET.SubElement(quiz, "intro"); ET.SubElement(intro, "text").text = intro_html or ""
    ET.SubElement(quiz, "introformat").text = "1"

    # timings / behaviour (keep your values if you already set these)
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

    # review flags (safe defaults)
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

    # sections layout
    sections = ET.SubElement(quiz, "sections")
    if entry_ids:
        sec = ET.SubElement(sections, "section", {"id": "1"})
        ET.SubElement(sec, "firstslot").text = "1"
        ET.SubElement(sec, "shufflequestions").text = "0"

    # totals (must match slots)
    total = 0.0
    ET.SubElement(quiz, "sumgrades").text = "0.00000"
    ET.SubElement(quiz, "grade").text = "0.00000"   # ← make grade zero if there are no slots

    # admin bits
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

    # containers that can be empty
    ET.SubElement(quiz, "subplugin_quizaccess_seb_quiz")
    ET.SubElement(quiz, "quiz_grade_items")
    ET.SubElement(quiz, "feedbacks")
    ET.SubElement(quiz, "overrides")
    ET.SubElement(quiz, "grades")
    ET.SubElement(quiz, "attempts")

    return _et_to_bytes(root)



def build_module_xml(moduleid: int, sectionnumber: int = 1,
                     visible: int = 1, visibleoncoursepage: int = 1,
                     modname: str = "Quiz") -> bytes:
    root = ET.Element("module", {"id": str(moduleid), "version": "2024100700"})
    ET.SubElement(root, "modulename").text = "quiz"
    ET.SubElement(root, "name").text = modname

    # IMPORTANT: sectionid is a DB id and must be remapped during restore
    ET.SubElement(root, "sectionid").text = "$@NULL@$"   # ← was "1"
    ET.SubElement(root, "sectionnumber").text = str(sectionnumber)

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

    
def build_moodle_backup_xml(moduleid: int, quiz_title: str, original_wwwroot: str = "https://example.invalid") -> bytes:
    root = ET.Element("moodle_backup")
    info = ET.SubElement(root, "information")

    stamp = time.strftime("%Y%m%d-%H%M", time.localtime())
    ET.SubElement(info, "name").text = f"backup-moodle2-activity-{moduleid}-quiz{moduleid}-{stamp}.mbz"
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

    # REQUIRED: type/format live under details/detail
    details = ET.SubElement(info, "details")
    detail = ET.SubElement(details, "detail", {"backup_id": f"id_{_uniq_suffix()}"})
    ET.SubElement(detail, "type").text = "activity"
    ET.SubElement(detail, "format").text = "moodle2"
    ET.SubElement(detail, "interactive").text = "1"
    ET.SubElement(detail, "mode").text = "10"
    ET.SubElement(detail, "execution").text = "1"
    ET.SubElement(detail, "executiontime").text = "0"

    # Contents map (points to the quiz folder we create)
    contents = ET.SubElement(info, "contents")
    activities = ET.SubElement(contents, "activities")
    act = ET.SubElement(activities, "activity")
    ET.SubElement(act, "moduleid").text = str(moduleid)
    ET.SubElement(act, "sectionid").text = "$@NULL@$"
    ET.SubElement(act, "modulename").text = "quiz"
    ET.SubElement(act, "title").text = quiz_title or "Quiz"
    ET.SubElement(act, "directory").text = f"activities/quiz_{moduleid}"
    ET.SubElement(act, "insubsection").text = ""

    # ✅ NEW: settings that control those checkboxes in the restore wizard
    # These are exactly what your working backup had (activities=1, and module-specific include flag).
    settings = ET.SubElement(info, "settings")
    
    def add_root_setting(name: str, value: str):
        s = ET.SubElement(settings, "setting")
        ET.SubElement(s, "level").text = "root"
        ET.SubElement(s, "name").text = name
        ET.SubElement(s, "value").text = value

    def add_activity_setting(activitykey: str, name: str, value: str):
        s = ET.SubElement(settings, "setting")
        ET.SubElement(s, "level").text = "activity"
        ET.SubElement(s, "activity").text = activitykey     # e.g. "quiz_5000"
        ET.SubElement(s, "name").text = name                 # e.g. "quiz_5000_included"
        ET.SubElement(s, "value").text = value
        
    def add_setting(name: str, value: str):
        s = ET.SubElement(settings, "setting")
        ET.SubElement(s, "level").text = "root"
        ET.SubElement(s, "name").text = name
        ET.SubElement(s, "value").text = value

    add_root_setting("filename", f"backup-moodle2-activity-{moduleid}-quiz{moduleid}-{stamp}.mbz")
    add_root_setting("users", "0")
    add_root_setting("anonymize", "0")
    add_root_setting("role_assignments", "0")
    add_root_setting("activities", "1")
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

    # ✅ activity-level flags (this is what flips the “Include activities” per-module)
    activitykey = f"quiz_{moduleid}"
    add_activity_setting(activitykey, f"{activitykey}_included", "1")
    add_activity_setting(activitykey, f"{activitykey}_userinfo", "0")

    # empty <settings> was already present before; we now fill it properly
    return _et_to_bytes(root)



def build_quiz_mbz(category_name: str,
                   questions: List[Dict[str, Any]],
                   quiz_name: str,
                   intro_html: str = "",
                   moduleid: int = 5000) -> bytes:

    # entry ids mirror questions.xml allocation (2000..)
    entry_ids = [2000 + i for i in range(len(questions))]

    questions_xml = build_questions_xml(category_name, questions)
    build_quiz_activity_xml._questions = questions
    quiz_xml = build_quiz_activity_xml(moduleid, quiz_name, intro_html)
    del build_quiz_activity_xml._questions
    # give module.xml the *same* display name as the quiz
    module_xml_bytes = build_module_xml(moduleid)
    # quick patch-in of <name> text to match quiz_name
    # (safe because we control the XML; or rewrite build_module_xml to accept name)
    mod_root = ET.fromstring(module_xml_bytes)
    for n in mod_root.findall("name"):
        n.text = quiz_name or "Quiz"
    module_xml = _et_to_bytes(mod_root)

    backup_xml = build_moodle_backup_xml(moduleid, quiz_name)


    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("moodle_backup.xml", backup_xml)
        z.writestr("questions.xml", questions_xml)
        z.writestr(f"activities/quiz_{moduleid}/quiz.xml", quiz_xml)
        z.writestr(f"activities/quiz_{moduleid}/module.xml", module_xml)

        # optional stubs
        z.writestr("roles.xml", "<roles></roles>")
        z.writestr("users.xml", "<users></users>")
        z.writestr("outcomes.xml", "<outcomes></outcomes>")
        z.writestr("groups.xml", "<groups></groups>")
        z.writestr("scales.xml", "<scales></scales>")
        z.writestr("files.xml", "<files></files>")
        z.writestr("completion.xml", "<completion></completion>")
        z.writestr("badges.xml", "<badges></badges>")
    return buf.getvalue()
        # --- populate question instances from the passed-in list (if any) ---
    total = 0.0
    qlist = getattr(build_quiz_activity_xml, "_questions", None)
    if qlist:
        q_instances = ET.SubElement(quiz, "question_instances")
        for idx, _ in enumerate(qlist, start=1):
            qi = ET.SubElement(q_instances, "question_instance", {"id": str(idx)})

            # These fields appear in real exports and are harmless when NULL
            # Moodle remaps quizid/gradeitemid during restore.
            ET.SubElement(qi, "quizid").text = "$@NULL@$"
            ET.SubElement(qi, "slot").text = str(idx)
            ET.SubElement(qi, "page").text = "1"
            ET.SubElement(qi, "displaynumber").text = "$@NULL@$"
            ET.SubElement(qi, "requireprevious").text = "0"
            ET.SubElement(qi, "maxmark").text = "1.0000000"
            ET.SubElement(qi, "quizgradeitemid").text = "$@NULL@$"

            ref = ET.SubElement(qi, "question_reference", {"id": str(1000 + idx)})
            ET.SubElement(ref, "usingcontextid").text = "$@NULL@$"
            ET.SubElement(ref, "component").text = "mod_quiz"
            ET.SubElement(ref, "questionarea").text = "slot"
            ET.SubElement(ref, "questionbankentryid").text = str(2000 + idx - 1)  # matches questions.xml
            ET.SubElement(ref, "version").text = "$@NULL@$"

            total += 1.0

        # One section covering all slots
        sections = ET.SubElement(quiz, "sections")
        sec = ET.SubElement(sections, "section", {"id": "1"})
        ET.SubElement(sec, "firstslot").text = "1"
        ET.SubElement(sec, "shufflequestions").text = "0"
    else:
        ET.SubElement(quiz, "question_instances")
        ET.SubElement(quiz, "sections")

    # --- keep other tags you already set above, but fix review flags + totals ---
    # Review flags: align with typical exports (safe defaults)
    for name, val in {
        "reviewattempt": "65536",
        "reviewcorrectness": "0",
        "reviewmarks": "4352",
        "reviewspecificfeedback": "0",
        "reviewgeneralfeedback": "0",
        "reviewrightanswer": "0",
        "reviewoverallfeedback": "0",
    }.items():
        node = quiz.find(name)
        if node is None:
            ET.SubElement(quiz, name).text = val
        else:
            node.text = val

    # Grading totals: sum of slot maxmarks; grade=100 is standard
    sg = quiz.find("sumgrades")
    if sg is None:
        sg = ET.SubElement(quiz, "sumgrades")
    sg.text = f"{total:.5f}"

    g = quiz.find("grade")
    if g is None:
        g = ET.SubElement(quiz, "grade")
    g.text = "100.00000"
