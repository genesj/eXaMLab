# Moodle Quiz Generator (`.mbz`)

This project is a Python desktop application for creating Moodle quizzes and packaging them into a Moodle Backup (`.mbz`) file for easy import.

## Core Components

The project consists of two main Python files:

1.  **`examlab_v1_1.py`**: This is the main entry point and contains the GUI for the application, built using `tkinter`. It allows users to define questions of various types (Multiple Choice, True/False, Short Answer, Essay). The `questionBuilder` class is the core of the UI, managing the question list and user inputs.

2.  **`mbz_builder.py`**: This script is the engine that generates the Moodle backup file (`.mbz`). It contains functions to build the necessary XML files (`questions.xml`, `quiz.xml`, `module.xml`, `moodle_backup.xml`) and package them into a `.zip` archive with a `.mbz` extension.

## Architecture and Data Flow

1.  **User Input**: The user creates questions through the `tkinter` interface in `examlab_v1_1.py`. Each question is stored as a dictionary in the `questions` list within the `questionBuilder` instance.

2.  **Data Structure for Questions**: A question is represented as a Python dictionary. The keys vary depending on the question type, but common keys include `type`, `name`, `text`, and `points`. For example, a multiple-choice question includes `options` and `correct` keys.

    ```python
    # Example of a Multiple Choice question dictionary
    {
        "type": "Multiple Choice",
        "name": "Question 1",
        "text": "What is the capital of France?",
        "options": ["Paris", "London", "Berlin"],
        "correct": [1], # 1-based index
        "points": 1.0
    }
    ```

3.  **Generating the `.mbz` file**:
    - When the user clicks "Save as XML" (which is slightly misnamed, as it saves as `.mbz`), the `save_as_xml` method in `examlab_v1_1.py` calls the `build_quiz_mbz` function from `mbz_builder.py`.
    - `build_quiz_mbz` orchestrates the creation of the complete Moodle backup structure. It generates several XML files by calling other functions within `mbz_builder.py`.
    - The generated XML files are then written into a zip archive, which is saved with the `.mbz` extension.

## Key Files and Logic

-   **`examlab_v1_1.py`**:
    -   `questionBuilder` class: Manages the UI for creating questions.
    -   `add_question()`: Gathers data from the UI and creates the question dictionary.
    -   `save_as_xml()`: Initiates the process of saving the quiz.

-   **`mbz_builder.py`**:
    -   `build_quiz_mbz()`: The main function that creates the `.mbz` file.
    -   `build_questions_xml()`: Creates the `questions.xml` file, which contains the question bank.
    -   `build_quiz_activity_xml()`: Creates `quiz.xml`, defining the quiz activity itself.
    -   `build_module_xml()`: Creates `module.xml`.
    -   `build_moodle_backup_xml()`: Creates `moodle_backup.xml`, the main manifest for the backup.

## Developer Workflow

-   The application is written in pure Python with `tkinter` for the UI.
-   There are no external dependencies besides `tkcalendar`.
-   To run the application, execute `examlab_v1_1.py` with a Python 3.12+ interpreter.
-   Logging is implemented, with logs being saved to platform-specific locations (`%APPDATA%/eXaMLab/logs` on Windows, `~/Library/Logs/eXaMLab` on macOS).

When making changes, be mindful of the data structures passed from the UI to the `.mbz` builder and the specific XML structures Moodle expects. The `mbz_builder.py` file is particularly sensitive to the XML schema required by Moodle.
