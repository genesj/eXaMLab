# Copilot Instructions for eXaMLab

## Project Overview
- **eXaMLab** is a Python desktop utility for building Moodle-compatible course content (quizzes, assignments, and question banks) via a Tkinter GUI. It targets educators who want to create and assemble full courses offline and import them into Moodle.
- The main script is `examlab_v1_1.py`. There are legacy versions in the `archive/` directory.
- The application is cross-platform (Windows, MacOS, Linux) and requires Python 3.12+ if run from source. No external dependencies except `tkcalendar`.

## Current and Planned Features
- **Current**: Full support for building and exporting question banks as Moodle XML.
- **Partial/Planned**: Assignment and quiz export UIs are present and under development; the goal is to support exporting assignments, quizzes, and question banks as separate or combined XML files for Moodle import.

## Architecture & Key Components
- **Single-file GUI app**: All main logic, UI, and data handling are in `examlab_v1_1.py`.
- **Major classes**:
  - `mainWindow`: App entry point and main window.
  - `questionBuilder`: For building and exporting question banks (Moodle XML).
  - `quizBuilder`: For assembling quizzes from question banks and setting quiz-level options (UI present, export logic in progress).
  - `assignmentBuilder`: For creating assignment XMLs (UI present, export logic in progress).
  - `forumBuilder`: Placeholder for future forum support.
- **Data flow**: User input is collected via Tkinter widgets, stored in in-memory lists, and exported as Moodle XML files.
- **No database or network**: All data is local and session-based.

## Developer Workflows
- **Run the app**: `python3 examlab_v1_1.py`
- **Build/packaging**: Not handled in this repo; see README for platform-specific packaging advice.
- **Testing**: No automated tests; manual testing via GUI is expected.
- **Debugging**: Logging is set up for errors and debug info. Logs are written to platform-specific locations (see `log_dir` in code).

## Project Conventions & Patterns
- **UI**: All UI is built with Tkinter and ttk. Tooltips are provided for most widgets.
- **XML Export**: Question and quiz data are exported in Moodle XML format. See `create_xml_content()` in `questionBuilder`.
- **Error handling**: Uses try/except blocks with logging for most user actions.
- **No type hints**: Code does not use Python type annotations.
- **No tests**: There are no unit or integration tests.
- **Legacy code**: Older versions are in `archive/` for reference.

## Integration & Dependencies
- **tkcalendar**: Only non-stdlib dependency. Used for date picking widgets.
- **No web or API integration**: All functionality is local.

## Examples & Patterns
- **Adding a new question type**: See how `questionBuilder` handles different types in `add_question()` and `update_ui_for_question_type()`.
- **Exporting XML**: See `create_xml_content()` for the XML structure.
- **Importing questions**: See `quizBuilder.import_xml()` for parsing Moodle XML files.

## Key Files
- `examlab_v1_1.py`: Main application logic and UI.
- `archive/examlab_v1.0.py`: Previous version for reference.
- `README.md`: User-facing documentation and requirements.

---

**When contributing code or using AI agents:**
- Follow the single-file, Tkinter-based structure unless refactoring is planned.
- Preserve cross-platform compatibility and avoid adding new dependencies unless necessary.
- Use the existing logging setup for error/debug output.
- Keep UI/UX consistent with current patterns (tooltips, grid layout, etc).
