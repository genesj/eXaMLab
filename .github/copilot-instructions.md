# Moodle Quiz Generator (`.mbz`)

This project is a Python desktop application for creating Moodle quizzes and packaging them into a Moodle Backup (`.mbz`) file for easy import. It's designed to be simple, portable, and dependency-light.

## Core Components and Architecture

1. **Main Application (`examlab_v1_1.py`)**
   - GUI implementation using `tkinter`
   - Core class `questionBuilder` handles question management and UI state
   - Integrated `mbz_builder` functions for generating Moodle backups

2. **Question Data Structure**
   ```python
   {
       "type": str,         # "Multiple Choice", "True/False", "Short Answer", "Essay"
       "name": str,         # Question title
       "text": str,         # Question content
       "points": float,     # Question points
       "options": list,     # [For Multiple Choice] List of answer choices
       "correct": list,     # [For Multiple Choice/True False] 1-based indices of correct answers
       "answer": str        # [For Short Answer] Correct answer text
   }
   ```

## Development Workflow

1. **Environment Setup**
   - Requires Python 3.12+ (critical for XML handling)
   - No pip dependencies except `tkcalendar` for date inputs
   - Logging: 
     - Windows: `%APPDATA%/eXaMLab/logs`
     - macOS: `~/Library/Logs/eXaMLab`
     - Linux: `/var/log/eXaMLab`

2. **Code Organization**
   - Core UI logic in `questionBuilder` class
   - `.mbz` generation functions prefixed with `build_` (e.g., `build_quiz_mbz()`)
   - XML utilities prefixed with `_` (e.g., `_indent_xml()`)

3. **Key Integration Points**
   - Question data flow: UI → Python dict → XML → `.mbz`
   - Moodle compatibility requires specific XML schemas (see `build_questions_xml()`)
   - Each question type has its own UI layout and validation rules

## Project Conventions

1. **XML Generation**
   - Never modify XML strings directly; use `xml.etree.ElementTree`
   - Required files: `questions.xml`, `quiz.xml`, `module.xml`, `moodle_backup.xml`
   - Use `_indent_xml()` for consistent formatting

2. **Error Handling**
   - Log errors before displaying them to user
   - Use `messagebox` for user-facing errors
   - Validate question data before XML generation

## Common Development Tasks

1. **Adding New Question Types**
   - Add type-specific UI elements in `questionBuilder`
   - Implement validation in `add_question()`
   - Update XML generation in `build_questions_xml()`

2. **Debugging**
   - Check logs for XML generation errors
   - Use `.get()` instead of direct dictionary access for UI values
   - Validate `.mbz` structure with Moodle's import tool

## Limitations and Constraints

- No support for image embedding in questions
- No support for complex question types (Drag and Drop, Calculated, etc.)
- UI elements must have tooltips (project convention)
