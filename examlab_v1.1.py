import os
import logging
import platform
import tkinter as tk
from tkinter import messagebox, filedialog, ttk, Text
## Written by Gene Smith-James
## Version 1.1 - MacOS compatibility
basedir = os.path.dirname(__file__)
# Windows-specific settings
if platform.system() == "Windows":
    try:
        from ctypes import windll  # Only exists on Windows
        myappid = 'xmlab'  # Arbitrary
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except ImportError:
        pass
## Logging - Cross-Platform (macOS/Linux & Windows)
## Thanks to Josh Manders
if platform.system() == "Windows":
    log_dir = os.path.join(os.getenv("APPDATA"), "eXaMLab", "logs")
else:  # macOS & Linux
    log_dir = os.path.expanduser("~/Library/Logs/eXaMLab")
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
class MoodleXMLBuilderApp:
    def __init__(self, root):
        try:
            self.root = root
            self.root.title("eXaMLab - Moodle XML Utility")
            #self.root.geometry("600x520")
            self.root.resizable(True, True)
            self.root.minsize(750, 630)
            if platform.system() == "Windows":
                self.root.iconbitmap(os.path.join(basedir, "icon.ico"))
            else:
                pass
            self.questions = []
            self.undo_stack = []
            self.edit_mode = False
            self.edit_index = None
            self.setup_ui()
            debug_logger.debug("User interface setup complete")
        except Exception as e:
            logging.error("Error initializing the application", exc_info=True)
            debug_logger.debug("Brutal error. Cannot initialize application.")
    def setup_ui(self):
        try:
            def validate_points(value_if_allowed):
                if value_if_allowed == "" or value_if_allowed.isdigit():
                    return True
                try:
                    float(value_if_allowed)
                    return True
                except ValueError:
                    return False
            vcmd = (self.root.register(validate_points), '%P')
            self.label_category = tk.Label(self.root, text="Enter Category Name:", anchor='e')
            self.label_category.grid(row=0, column=0, padx=10, pady=5, sticky='e')
            self.entry_category = tk.Entry(self.root, width=50)
            self.entry_category.grid(row=0, column=1, padx=10, pady=5, sticky='we', columnspan=2)
            Tooltip(self.entry_category, "Enter the name of this question bank. This will be used as the category these questions belong to inside of Moodle. You can only have one category per XML file.")
            debug_logger.debug("Category input field initialized.")
##You can actually have multiple categories in a MoodleXML file.
##Right now, the program is configured to only let you do one overarching category for the entire bank.
            self.label_question_type = tk.Label(self.root, text="Select Question Type:", anchor='e')
            self.label_question_type.grid(row=1, column=0, padx=10, pady=5, sticky='e')
            self.question_type_var = tk.StringVar(value="Multiple Choice")
            self.dropdown_question_type = ttk.Combobox(self.root, textvariable=self.question_type_var, values=["Multiple Choice", "True/False", "Short Answer", "Essay", "Cloze"])
            self.dropdown_question_type.bind("<<ComboboxSelected>>", lambda event: self.update_ui_for_question_type(self.question_type_var.get()))
            self.dropdown_question_type.state(["readonly"])  # Make it read-only to simulate an OptionMenu behavior
            self.dropdown_question_type.grid(row=1, column=1, padx=10, pady=5, sticky='w')
            Tooltip(self.dropdown_question_type, "Select the type of question you want to create. The controls will update based on the selected question type.")
            debug_logger.debug("Question type dropdown initialized.")
            self.label_question_name = tk.Label(self.root, text="Enter Question Title:", anchor='e')
            self.label_question_name.grid(row=2, column=0, padx=10, pady=5, sticky='e')
            self.entry_question_name = tk.Entry(self.root, width=50)
            self.entry_question_name.grid(row=2, column=1, padx=10, pady=5, columnspan=2, sticky='we')
            Tooltip(self.entry_question_name, "Enter a title for the question. This will be displayed as the Question Name in Moodle.\n\nNote that Question Name is NOT the same thing as the text of the question. Question Names are purely cosmetic and only seeen by the instructor.")
            debug_logger.debug("Question name input field initialized.")
            self.label_question_text = tk.Label(self.root, text="Enter Question Text:", anchor='e')
            self.label_question_text.grid(row=3, column=0, padx=10, pady=5, sticky='e')
            self.entry_question_text = tk.Text(self.root, width=50, height=4)
            self.entry_question_text.grid(row=3, column=1, padx=10, pady=5, sticky='we', columnspan=2)
            Tooltip(self.entry_question_text, "Enter the text of the question.")
            debug_logger.debug("Question text input field initialized.")
            self.label_points = tk.Label(self.root, text="Point Value (default is 1):", anchor='e')
            self.label_points.grid(row=5, column=0, padx=10, pady=5, sticky='e')
            self.entry_points = tk.Entry(self.root, width=10, validate='key', validatecommand=vcmd)
            self.entry_points.grid(row=5, column=1, sticky='w', padx=10, pady=5)
            self.entry_points.insert(0, "1")  # Default value for points is 1
            Tooltip(self.entry_points, "Enter the point value for this question.\n\nThis value is used as the default grade for the question in Moodle. This isn't really necessary to set, depending on how your quiz is going to be configured.\nMoodle figures out how many points each question should be worth based on the Maximum Grade you set for the quiz.\n\nIn short, this is purely personal preference.")
            debug_logger.debug("Points input field initialized.")
            self.label_mcq_options = tk.Label(self.root, text="Possible Choices:", anchor='e')
            self.label_mcq_options.grid(row=6, column=0, padx=10, pady=5, sticky='e')
            self.entry_mcq_options = tk.Entry(self.root, width=50)
            self.entry_mcq_options.grid(row=6, column=1, padx=10, pady=5, columnspan=2, sticky='we')
            Tooltip(self.entry_mcq_options, "Enter the options for the multiple-choice question, separated by commas. Choices will be shuffled inside Moodle.\n\nExample: Choice 1,Choice 2,Choice 3,Choice 4\nDo not include spaces after commas. Spaces within choices are allowed.")
            debug_logger.debug("Multiple choice options input field initialized.")
            self.label_correct_option = tk.Label(self.root, text="Correct Answer(s)", anchor='e')
            self.label_correct_option.grid(row=7, column=0, padx=10, pady=5, sticky='e')
            self.entry_correct_option = tk.Entry(self.root, width=50)
            self.entry_correct_option.grid(row=7, column=1, padx=10, pady=5, columnspan=2, sticky='we')
            Tooltip(self.entry_correct_option, "Enter the number(s) corresponding to the correct option(s), separated by commas.\n\nExample: 1,3\nThis would mean the first and third options are correct.")
            debug_logger.debug("Correct option input field initialized.")
            self.label_short_answer_correct = tk.Label(self.root, text="Enter Correct Short Answer:", anchor='e')
            self.label_short_answer_correct.grid(row=8, column=0, padx=10, pady=5, sticky='e')
            self.entry_short_answer_correct = tk.Entry(self.root, width=50)
            self.entry_short_answer_correct.grid(row=8, column=1, padx=10, pady=5)
            Tooltip(self.entry_short_answer_correct, "Enter the correct answer for the short answer question.\n\nShort Answer questions are very sensitive to spelling and punctuation. \nBe sure to enter the correct answer EXACTLY as you want it to be entered by students.\n\nWildcards are supported: you can replace a character with an asterisk * to act as a placeholder for any possible character that could be used. \nThis can let you account for alternative spellings.\n\nIf the question doesn't have a definitive answer, you should use the Essay question type instead. \nEssay questions are open-ended and give the student a blank text box to write in.")
            debug_logger.debug("Short answer input field initialized.")
            self.label_tf_answer = tk.Label(self.root, text="Select True/False:", anchor='e')
            self.label_tf_answer.grid(row=9, column=0, padx=10, pady=5, sticky='e')
            self.tf_var = tk.StringVar(value="True")
            self.radio_true = tk.Radiobutton(self.root, text="True", variable=self.tf_var, value="True")
            self.radio_true.grid(row=9, column=1, sticky='w')
            self.radio_false = tk.Radiobutton(self.root, text="False", variable=self.tf_var, value="False")
            self.radio_false.grid(row=9, column=1, sticky='e')
            Tooltip(self.radio_true, "Select if the answer is True.")
            Tooltip(self.radio_false, "Select if the answer is False.")
            debug_logger.debug("True/False radio buttons initialized.")
            #self.buttton_bug_report = tk.Button(self.root, text="Report Issues", command=self.bug_report)
            #self.buttton_bug_report.grid(row=10, column=0, padx=10, pady=5, sticky='w')
            self.button_cloze_editor = tk.Button(self.root, text="Open Cloze Editor", command=self.cloze_editor)
            self.button_cloze_editor.grid(row=4, column=1, padx=10, pady=5, columnspan=2, sticky='we')
            self.button_add_question = tk.Button(self.root, text="Add Question", command=self.add_question)
            self.button_add_question.grid(row=11, column=1, padx=10, pady=5, sticky='nesw')
            Tooltip(self.button_add_question, "Click to add the current question to your question bank.")
            debug_logger.debug("Add question button initialized.")
            self.button_edit_question = tk.Button(self.root, text="Edit Question", command=self.edit_question, state=tk.DISABLED)
            self.button_edit_question.grid(row=11, column=0, padx=5, pady=5, sticky='nesw')
            Tooltip(self.button_edit_question, "Select a question from the list below. Then, use this button to edit the selected question.")
            debug_logger.debug("Edit question button initialized.")
            self.button_delete_question = tk.Button(self.root, text="Delete Question(s)", command=self.delete_selected_questions)
            self.button_delete_question.grid(row=11, column=2, padx=5, pady=5, sticky='nesw')
            Tooltip(self.button_delete_question, "Click to delete the selected questions from the list.")
            debug_logger.debug("Delete question button initialized.")
            self.listbox_questions = tk.Listbox(self.root, selectmode=tk.EXTENDED)
            self.listbox_questions.grid(row=12, column=0, columnspan=3, padx=10, pady=10, sticky='nsew')
            self.listbox_questions.bind('<<ListboxSelect>>', self.on_question_select)
            self.root.grid_rowconfigure(12, weight=1)
            self.root.grid_columnconfigure(0, weight=1)
            self.root.grid_columnconfigure(1, weight=1)
            self.root.grid_columnconfigure(2, weight=1)
            debug_logger.debug("Question listbox initialized.")
            self.button_save_xml = tk.Button(self.root, text="Save as XML", command=self.save_as_xml)
            self.button_save_xml.grid(row=13, column=0, columnspan=3, pady=5)
            Tooltip(self.button_save_xml, "Click to save all the questions as an XML file.")
            debug_logger.debug("Save as XML button initialized.")
            self.update_ui_for_question_type("Multiple Choice")
            debug_logger.debug("UI finished initializing. Setting initial question type.")
        except Exception as e:
            logging.error("Error setting up the user interface", exc_info=True)
            debug_logger.debug("UI Error. See error_log.txt for details.")
    def on_question_select(self, event):
        if self.listbox_questions.curselection():
            self.button_edit_question.config(state=tk.NORMAL)
        else:
            self.button_edit_question.config(state=tk.DISABLED)
    def update_ui_for_question_type(self, question_type):
        try:
            self.label_mcq_options.grid()
            self.entry_mcq_options.grid()
            self.label_correct_option.grid()
            self.entry_correct_option.grid()
            self.label_short_answer_correct.grid()
            self.entry_short_answer_correct.grid()
            self.label_tf_answer.grid()
            self.radio_true.grid()
            self.radio_false.grid()
            self.label_mcq_options.grid_remove()
            self.entry_mcq_options.grid_remove()
            self.label_correct_option.grid_remove()
            self.entry_correct_option.grid_remove()
            self.label_short_answer_correct.grid_remove()
            self.entry_short_answer_correct.grid_remove()
            self.label_tf_answer.grid_remove()
            self.radio_true.grid_remove()
            self.radio_false.grid_remove()
            if question_type == "Multiple Choice":
                self.label_mcq_options.grid()
                self.entry_mcq_options.grid()
                self.label_correct_option.grid()
                self.entry_correct_option.grid()
                debug_logger.debug("QuestionType Multiple Choice selected.")
            elif question_type == "True/False":
                self.label_tf_answer.grid()
                self.radio_true.grid()
                self.radio_false.grid()
                debug_logger.debug("QuestionType True/False selected.")
            elif question_type == "Short Answer":
                self.label_short_answer_correct.grid()
                self.entry_short_answer_correct.grid()
                debug_logger.debug("QuestionType Short Answer selected.")
            elif question_type == "Essay":
                debug_logger.debug("QuestionType Essay selected.")
            elif question_type == "Cloze":
                debug_logger.debug("QuestionType Cloze selected.")
        except Exception as e:
            logging.error("Error updating UI for question type", exc_info=True)
            debug_logger.debug("UI Error. See error_log.txt for details.")



##Bug Report button, commits to a text file
   # def bug_report(self):
    #    try:
     #       bug_window = tk.Toplevel(self.root)
      #      bug_window.title("Issue Report")
       #     bug_window.geometry("400x300")
        #    text_box = tk.Text(bug_window, wrap='word', width=40, height=10)
         #   text_box.pack(expand=True, fill='both', padx=10, pady=10)
          #  label = tk.Label(bug_window, text="Pressing Submit will save your report as an entry in bug_report.txt.\nYou can submit multiple issues.", anchor='w')
           # label.pack(pady=10)
           # def submit_bug_report():
           #     bug_report_text = text_box.get("1.0", tk.END).strip()
           #     if bug_report_text:
           #         with open("bug_report.txt", "a", encoding='utf-8') as file:
           #             with open("bug_report.txt", "a") as file:
           #                 file.write(f"{bug_report_text}\n---\n")
           #         bug_window.destroy()
           #         debug_logger.debug("Issue report submitted.")
           #     else:
           #         messagebox.showwarning("Issue Report", "Please enter a issue report before submitting.")
           # submit_button = tk.Button(bug_window, text="Submit", command=submit_bug_report)
           # submit_button.pack(pady=10)
           # debug_logger.debug("Issue report window opened.")
        #except Exception as e:
         #   logging.error("Error opening issue report window", exc_info=True)
          #  debug_logger.error("UI Error. See error_log.txt for details.", exc_info=True)



    def add_question(self):
        try:
            question_type = self.question_type_var.get()
            question_name = self.entry_question_name.get()
            question_text = self.entry_question_text.get("1.0", tk.END).strip()
            points = self.entry_points.get()
            points = float(points) if points else 1.0  # Default to 1 point if not specified
            if question_type == "Multiple Choice":
                options_text = self.entry_mcq_options.get()
                correct_options_text = self.entry_correct_option.get()
                if question_name and question_text and options_text and correct_options_text:
                    options = [opt.strip() for opt in options_text.split(',')]
                    correct_options = [int(opt.strip()) for opt in correct_options_text.split(',')]
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
            self.entry_mcq_options.delete(0, tk.END)
            self.entry_correct_option.delete(0, tk.END)
            self.entry_short_answer_correct.delete(0, tk.END)
            self.edit_mode = False
            self.edit_index = None
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
            for question in self.questions:
                display_text = f"{question['type']}: {question['name']} - {question['text']} (Points: {question['points']})"
                self.listbox_questions.insert(tk.END, display_text)
        except Exception as e:
            logging.error("Error updating question list", exc_info=True)
    def edit_question(self):
        try:
            selected_indices = list(self.listbox_questions.curselection())
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
                self.entry_mcq_options.delete(0, tk.END)
                self.entry_mcq_options.insert(0, ', '.join(question['options']))
                self.entry_correct_option.delete(0, tk.END)
                self.entry_correct_option.insert(0, ', '.join(map(str, question['correct'])))
            elif question['type'] == "True/False":
                self.tf_var.set(question['answer'])
            elif question['type'] == "Short Answer":
                self.entry_short_answer_correct.delete(0, tk.END)
                self.entry_short_answer_correct.insert(0, question['correct_answer'])
            self.edit_mode = True
            self.edit_index = index
            self.button_delete_question.config(state=tk.DISABLED)
        except Exception as e:
            logging.error("Error editing question", exc_info=True)
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
                    xml_content += f"  <question type=\"essay\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n  </question>\n"
                elif question['type'] == "Cloze":
                    xml_content += f" <question type=\"cloze\">\n    <name>\n      <text>{question['name']}</text>\n    </name>\n    <questiontext format=\"html\">\n      <text><![CDATA[{question['text']}]]></text>\n    </questiontext>\n    <defaultgrade>{question['points']}</defaultgrade>\n  </question>\n"
            xml_content += "</quiz>"
            return xml_content
        except Exception as e:
            logging.error("Error creating XML content", exc_info=True)
            return ""
        

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
            cloze_options = ["Multichoice", "Short Answer", "Numerical"]
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

            def build_cloze_string():
                weight = cloze_weight_entry.get().strip() or "100"
                corrects = [e.get().strip() for e in correct_answer_entries if e.get().strip()]
                wrongs = [e.get().strip() for e in wrong_answer_entries if e.get().strip()]
                cloze_type = cloze_type_var.get().upper().replace(" ", "")
                # Build answer string
                answer_parts = []
                for c in corrects:
                    answer_parts.append(f"={c}")
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


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = MoodleXMLBuilderApp(root)
        root.mainloop()
    except Exception as e:
        logging.error("Fatal error in main application loop", exc_info=True)
